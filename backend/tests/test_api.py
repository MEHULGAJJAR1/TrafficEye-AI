import csv
import io
import json
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.app.config import ROOT
from backend.app.database import Database
from backend.app.main import create_app
from conftest import TEST_KEY, complete_demo, sample, wait_job


def test_auth_required_for_all_private_data(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/health').status_code == 200
        assert not c.get('/api/auth/status').json()['authenticated']
        for path in ['/api/jobs', '/api/system', '/api/analytics', '/api/reports.csv', f'/api/evidence/{uuid4()}']:
            assert c.get(path).status_code == 401
        result = c.post('/api/auth/login', json={'key': TEST_KEY})
        assert result.status_code == 200
        assert 'HttpOnly' in result.headers['set-cookie']
        assert 'SameSite=strict' in result.headers['set-cookie']
        assert c.get('/api/jobs').status_code == 200
        assert c.post('/api/auth/logout').status_code == 200
        assert c.get('/api/jobs').status_code == 401


def test_bearer_key_and_forged_cookie(settings):
    with TestClient(create_app(settings)) as c:
        c.cookies.set('te_session', '999999999999.fake.invalid')
        assert c.get('/api/jobs').status_code == 401
        assert c.get('/api/jobs', headers={'Authorization': f'Bearer {TEST_KEY}'}).status_code == 200


def test_login_rate_limit(settings):
    with TestClient(create_app(settings)) as c:
        for _ in range(10):
            assert c.post('/api/auth/login', json={'key': 'wrong'}).status_code == 401
        assert c.post('/api/auth/login', json={'key': TEST_KEY}).status_code == 429


def test_csrf_origin_is_rejected(client):
    assert client.post('/api/samples/demo', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.options('/api/uploads', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST'}).status_code == 200


def test_upload_rejects_bad_types_empty_corrupt_and_oversize(client):
    assert client.post('/api/uploads', files={'file': ('x.txt', b'not-video')}).status_code == 415
    assert client.post('/api/uploads', files={'file': ('x.mp4', b'')}).status_code == 422
    assert client.post('/api/uploads', files={'file': ('x.mp4', b'not-a-video')}).status_code == 422
    assert client.post('/api/uploads', files={'file': ('x.mp4', b'a' * (1024 * 1024 + 100))}).status_code == 413
    assert client.post('/api/uploads', content='x', headers={'Content-Length': '5000000'}).status_code == 413
    assert not list((client.app.state.settings.data_dir / 'uploads').iterdir())


def test_demo_full_workflow_upload_tracking_snapshot_csv(client):
    path = ROOT / 'samples' / 'traffic_demo_60s.mp4'
    with path.open('rb') as file:
        response = client.post('/api/uploads', files={'file': ('../../traffic.mp4', file, 'video/mp4')})
    assert response.status_code == 201, response.text
    job = response.json()
    assert job['filename'] == 'traffic.mp4' and job['is_demo_source']
    assert job['duration'] == 60 and job['preview_status'] == 'ready'
    assert 'source_path' not in job
    rejected = client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'real', 'max_seconds': 6})
    assert rejected.status_code == 409 and 'missing' in rejected.json()['detail'].lower()
    start = client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo', 'max_seconds': 6})
    assert start.status_code == 200
    with client.websocket_connect(f"/api/ws/jobs/{job['id']}") as ws:
        packet = ws.receive_json()
        assert packet['type'] == 'job_update' and packet['job']['mode'] == 'demo'
    result = wait_job(client, job['id'])
    assert result['status'] == 'completed', result
    assert result['processed_frames'] == 72
    assert result['progress'] == 1 and result['processing_fps'] > 0
    assert result['inference_fps'] == 0  # scripted demo never reports model inference
    assert result['last_result']['detections']
    frames = client.get(f"/api/jobs/{job['id']}/results?limit=100").json()
    assert frames['total'] == 72 and frames['items'][0]['payload']['mode'] == 'demo'
    tracks = client.get('/api/tracks', params={'job_id': job['id']}).json()
    assert tracks['total'] >= 4
    assert any(t['observations'] > 8 for t in tracks['items'])
    violations = client.get('/api/violations', params={'job_id': job['id']}).json()
    assert violations['total'] > 0
    for item in violations['items']:
        assert item['votes'] >= 4 and item['confidence'] >= .65
        assert item['mode'] == 'demo'
        image = client.get(item['evidence_url'])
        assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
        decoded = cv2.imdecode(np.frombuffer(image.content, np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[:2] == (540, 960)
    assert client.get(f"/api/jobs/{job['id']}/frame").status_code == 200
    video = client.get(f"/api/jobs/{job['id']}/video", headers={'Range': 'bytes=0-99'})
    assert video.status_code == 206 and len(video.content) == 100
    for kind in ['violations', 'vehicles']:
        report = client.get('/api/reports.csv', params={'job_id': job['id'], 'kind': kind})
        assert report.status_code == 200 and 'attachment' in report.headers['content-disposition']
        rows = list(csv.DictReader(io.StringIO(report.content.decode('utf-8-sig'))))
        assert rows and all(row['source_mode'] == 'demo' for row in rows)
        assert {'vehicle_id', 'timestamp_utc', 'vehicle_class', 'helmet_status', 'seatbelt_status', 'violation_type', 'confidence', 'zone', 'evidence_filename'} <= rows[0].keys()
    stats = client.get('/api/analytics', params={'job_id': job['id']}).json()['summary']
    assert stats['total_vehicles'] == tracks['total']
    assert stats['detection_events'] == result['detection_events']
    assert stats['confirmed_violations'] == violations['total']
    assert stats['violation_rate'] == round(100 * stats['unique_violating_vehicles'] / tracks['total'], 2)
    persisted = Database(client.app.state.settings.data_dir / 'trafficeye.sqlite3')
    assert persisted.job(job['id'])['processed_frames'] == 72
    assert persisted.one('SELECT COUNT(*) AS n FROM violations WHERE job_id=?', (job['id'],))['n'] == violations['total']


def test_filters_and_timestamp_reference(client):
    job = sample(client)
    r = client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo', 'max_seconds': 6, 'recorded_at': '2026-10-20T10:00:00+05:30'})
    assert r.status_code == 200
    result = wait_job(client, job['id'])
    assert result['timestamp_basis'] == 'user-supplied'
    stats = client.get('/api/analytics', params={'job_id': job['id'], 'vehicle_class': 'Bike'}).json()
    assert stats['summary']['cars'] == 0
    assert stats['summary']['motorcycles'] == stats['summary']['total_vehicles']
    assert not client.get('/api/violations', params={'source': 'real'}).json()['items']
    assert not client.get('/api/tracks', params={'min_confidence': .999}).json()['items']
    assert client.get('/api/violations', params={'date_from': '2030-01-01T00:00:00Z'}).json()['total'] == 0
    assert client.get('/api/analytics', params={'date_from': '2026-01-01'}).status_code == 422
    assert client.get('/api/analytics', params={'date_from': '2030-01-01T00:00:00Z', 'date_to': '2020-01-01T00:00:00Z'}).status_code == 422
    v = client.get('/api/violations').json()['items'][0]
    assert v['occurred_at'].startswith('2026-10-20T04:30:')


def test_pause_resume_cancel_and_retry(client):
    client.app.state.settings.demo_delay = .025
    job = sample(client)
    path = f"/api/jobs/{job['id']}"
    assert client.post(path + '/start', json={'mode': 'demo', 'max_seconds': 6}).status_code == 200
    wait_job(client, job['id'], states=('running',))
    assert client.post(path + '/pause').status_code == 200
    time.sleep(.08)  # cooperative pause may finish the in-flight frame
    count = client.get(path).json()['processed_frames']
    time.sleep(.1)
    assert client.get(path).json()['processed_frames'] == count
    assert client.post(path + '/resume').status_code == 200
    assert client.post(path + '/cancel').status_code == 200
    assert wait_job(client, job['id'])['status'] == 'cancelled'
    assert client.post(path + '/retry', json={'mode': 'demo', 'max_seconds': 3}).status_code == 200
    done = wait_job(client, job['id'])
    assert done['status'] == 'completed' and done['processed_frames'] == 36
    assert client.get(path + '/results').json()['total'] == 36
    assert client.post(path + '/pause').status_code == 409


def test_bounded_queue_and_queued_cancellation(client):
    client.app.state.settings.demo_delay = .04
    jobs = [sample(client) for _ in range(3)]
    for job in jobs[:2]:
        assert client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo', 'max_seconds': 6}).status_code == 200
    assert client.post(f"/api/jobs/{jobs[2]['id']}/start", json={'mode': 'demo'}).status_code == 409
    assert client.post(f"/api/jobs/{jobs[1]['id']}/cancel").status_code == 200
    assert client.post(f"/api/jobs/{jobs[0]['id']}/cancel").status_code == 200
    assert wait_job(client, jobs[0]['id'])['status'] == 'cancelled'
    assert wait_job(client, jobs[1]['id'])['status'] == 'cancelled'


def test_invalid_start_control_and_configuration(client):
    job = sample(client)
    assert client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'pretend'}).status_code == 422
    assert client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo', 'max_seconds': 0}).status_code == 422
    assert client.post(f"/api/jobs/{job['id']}/pause").status_code == 409
    assert client.get(f'/api/jobs/{uuid4()}').status_code == 404
    assert client.get('/api/jobs/../../access.key').status_code in (404, 422)
    config = client.get('/api/config').json()
    config['frame_stride'] = 0
    assert client.put('/api/config', json=config).status_code == 422
    model = client.post('/api/model/validate').json()
    assert not model['ready'] and model['state'] == 'missing'


def test_unrelated_video_cannot_receive_scripted_detections(client, tmp_path):
    path = tmp_path / 'unrelated.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 12, (320, 240))
    for _ in range(24):
        writer.write(np.zeros((240, 320, 3), np.uint8))
    writer.release()
    with path.open('rb') as file:
        r = client.post('/api/uploads', files={'file': ('camera.avi', file, 'video/x-msvideo')})
    assert r.status_code == 201, r.text
    job = r.json()
    assert not job['is_demo_source']
    assert client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo'}).status_code == 409
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['preview_status'] != 'preparing':
            break
        time.sleep(.03)
    assert state['preview_status'] == 'ready'
    assert client.get(f"/api/jobs/{job['id']}/video").status_code == 200


def test_evidence_path_traversal_prevention(client):
    job = complete_demo(client, 3)
    item = client.get('/api/violations').json()['items'][0]
    with client.app.state.db.connect() as db:
        db.execute('UPDATE violations SET evidence_filename=? WHERE id=?', ('../../access.key', item['id']))
    assert client.get(item['evidence_url']).status_code == 400
    assert client.get(f'/api/evidence/{uuid4()}').status_code == 404


def test_delete_removes_owned_files_and_results(client):
    job = complete_demo(client, 3)
    root = client.app.state.settings.data_dir
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert not (root / 'uploads' / f"{job['id']}.mp4").exists()
    assert not (root / 'evidence' / job['id']).exists()
    assert not client.get('/api/tracks').json()['items']


def test_results_and_config_survive_application_restart(settings):
    with TestClient(create_app(settings)) as c:
        c.post('/api/auth/login', json={'key': TEST_KEY})
        job = complete_demo(c, 3)
        config = c.get('/api/config').json()
        config['imgsz'] = 704
        assert c.put('/api/config', json=config).status_code == 200
    with TestClient(create_app(settings)) as c:
        c.post('/api/auth/login', json={'key': TEST_KEY})
        assert c.get('/api/config').json()['imgsz'] == 704
        restored = c.get(f"/api/jobs/{job['id']}").json()
        assert restored['status'] == 'completed' and restored['processed_frames'] == 36
        assert c.get('/api/violations').json()['total'] > 0
        # Recovering a stale running record never presents it as a completed job.
        c.app.state.db.update_job(job['id'], status='running')
    with TestClient(create_app(settings)) as c:
        c.post('/api/auth/login', json={'key': TEST_KEY})
        assert c.get(f"/api/jobs/{job['id']}").json()['status'] == 'interrupted'


def test_mov_upload_full_video_and_explicit_frame_stride(client):
    path = ROOT / 'samples' / 'traffic_demo_60s.mp4'
    with path.open('rb') as file:
        response = client.post('/api/uploads', files={'file': ('sample.MOV', file, 'video/quicktime')})
    assert response.status_code == 201
    job = response.json()
    config = client.get('/api/config').json()
    config['frame_stride'] = 10
    assert client.put('/api/config', json=config).status_code == 200
    result = client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'demo', 'max_seconds': None})
    assert result.status_code == 200
    done = wait_job(client, job['id'])
    assert done['status'] == 'completed' and done['processed_frames'] == 72
    assert done['decoded_frames'] == done['target_frames'] == 720
    assert done['config']['frame_stride'] == 10 and done['options']['max_seconds'] is None


def test_chunked_oversize_and_websocket_unauthorized(settings):
    from starlette.websockets import WebSocketDisconnect
    import pytest
    with TestClient(create_app(settings)) as c:
        c.post('/api/auth/login', json={'key': TEST_KEY})
        # No Content-Length: exercise the ASGI receive counter, not only header checks.
        boundary = 'chunked-limit-test'
        prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()
        def body():
            yield prefix
            for _ in range(5):
                yield b'x' * (512 * 1024)
            yield f'\r\n--{boundary}--\r\n'.encode()
        assert c.post('/api/uploads', content=body(), headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}).status_code == 413
        job = sample(c)
        c.cookies.clear()
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"/api/ws/jobs/{job['id']}"):
                pass


def test_startup_cleans_crash_orphans_but_preserves_database(settings):
    settings.prepare()
    orphan = settings.data_dir / 'uploads' / f'{uuid4()}.mp4'
    orphan.write_bytes(b'partial unregistered upload')
    temp = settings.data_dir / 'frames' / 'partial.tmp'
    temp.write_bytes(b'incomplete jpeg')
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/health').status_code == 200
        assert not orphan.exists() and not temp.exists()
        assert (settings.data_dir / 'trafficeye.sqlite3').is_file()


def test_nonfinite_malformed_json_is_a_safe_validation_error(client):
    config = client.get('/api/config').json()
    config['confidence'] = float('nan')
    response = client.put('/api/config', content=json.dumps(config), headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert all('input' not in item for item in response.json()['detail'])
    assert client.post('/api/auth/login', content='{"key":', headers={'Content-Type': 'application/json'}).status_code == 422


def test_corrupt_sample_manifest_does_not_break_the_application(settings, tmp_path):
    import shutil
    folder = tmp_path / 'bad-sample'
    folder.mkdir()
    shutil.copy2(ROOT / 'samples/traffic_demo_60s.mp4', folder / 'traffic_demo_60s.mp4')
    (folder / 'demo_manifest.json').write_text('not json')
    settings.sample_dir = folder
    with TestClient(create_app(settings)) as c:
        c.post('/api/auth/login', json={'key': TEST_KEY})
        assert c.get('/api/health').status_code == 200
        assert c.get('/api/system').json()['sample_available'] is False
        assert c.post('/api/samples/demo').status_code == 409
