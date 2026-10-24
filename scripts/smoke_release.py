"""Extract a verified ZIP into a temporary workspace and run a real authenticated API round trip.

Requires this project's Python requirements-dev. --rebuild-frontend also needs Node/npm and
internet for npm ci. The child uses the EXTRACTED source and clean bundled schema, not the
working application's private data. It generates a temporary key and never reports its value.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_release import verify

PROBE = r'''
import csv, io, json, sqlite3, time
from pathlib import Path
import cv2
import numpy as np
from fastapi.testclient import TestClient
from backend.app.config import ROOT, Settings
from backend.app.main import create_app
assert ROOT.resolve() == Path.cwd().resolve(), 'Not using the extracted project source'
settings = Settings(demo_delay=0.001)
assert not (settings.data_dir / 'access.key').exists(), 'Release must not include a private key'
app = create_app(settings)
with TestClient(app) as c:
    assert c.get('/api/health').status_code == 200
    assert c.get('/api/docs').status_code == 200
    assert c.get('/api/openapi.json').status_code == 200
    assert c.get('/api/jobs').status_code == 401
    key = (settings.data_dir / 'access.key').read_text().strip()
    assert len(key) >= 24
    assert c.post('/api/auth/login', json={'key': key}).status_code == 200
    assert c.get('/api/jobs').json()['items'] == []
    assert c.get('/api/analytics').json()['summary']['total_vehicles'] == 0
    model = c.post('/api/model/validate').json()
    assert model['ready'] is False and 'missing' in model['message'].lower()
    with (settings.sample_dir / 'traffic_demo_60s.mp4').open('rb') as f:
        response = c.post('/api/uploads', files={'file': ('release-sample.mp4', f, 'video/mp4')})
    assert response.status_code == 201, response.text
    job = response.json()
    assert job['is_demo_source'] and job['duration'] == 60
    jid = job['id']
    response = c.post(f'/api/jobs/{jid}/start', json={'mode': 'demo', 'max_seconds': 3, 'recorded_at': '2026-10-23T10:00:00+05:30'})
    assert response.status_code == 200, response.text
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = c.get(f'/api/jobs/{jid}').json()
        if job['status'] in ('completed','failed','cancelled'):
            break
        time.sleep(.02)
    assert job['status'] == 'completed', job
    assert job['processed_frames'] == 36 and job['progress'] == 1
    assert job['inference_fps'] == 0 and job['mode'] == 'demo'
    assert job['recorded_at'].startswith('2026-10-23T04:30:00')
    assert c.get(f'/api/jobs/{jid}/frame').status_code == 200
    stats = c.get('/api/analytics', params={'job_id': jid}).json()
    records = c.get('/api/violations', params={'job_id': jid}).json()['items']
    assert records and stats['summary']['total_vehicles'] > 0
    evidence_id = records[0]['id']
    jpeg = c.get(f'/api/evidence/{evidence_id}')
    assert jpeg.status_code == 200 and jpeg.headers['content-type'].startswith('image/jpeg')
    decoded = cv2.imdecode(np.frombuffer(jpeg.content,np.uint8),cv2.IMREAD_COLOR)
    assert decoded is not None and decoded.shape[:2] == (540,960)
    csv_response = c.get('/api/reports.csv', params={'job_id': jid})
    assert csv_response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
    assert len(rows) == len(records) and all(row['source_mode'] == 'demo' and row['evidence_filename'] for row in rows)
    assert all(row['timestamp_basis'] == 'user-supplied' for row in rows)
    vehicle_rows = list(csv.DictReader(io.StringIO(c.get('/api/reports.csv', params={'job_id': jid, 'kind': 'vehicles'}).content.decode('utf-8-sig'))))
    assert len(vehicle_rows) == stats['summary']['total_vehicles']
    result = {'health_and_api_schema': 'passed', 'clean_empty_workspace': True, 'generated_private_key_length': len(key), 'missing_custom_model_is_explicit': True, 'uploaded_sample_duration_seconds': job['duration'], 'processed_span_seconds': 3, 'processed_frames': job['processed_frames'], 'mode': job['mode'], 'inference_fps': job['inference_fps'], 'unique_tracked_vehicles': stats['summary']['total_vehicles'], 'confirmed_scripted_records': len(records), 'evidence_jpeg_bytes': len(jpeg.content), 'evidence_image_dimensions': [decoded.shape[1], decoded.shape[0]], 'violation_csv_rows': len(rows), 'vehicle_csv_rows': len(vehicle_rows), 'supplied_timezone_converted_to_utc': True}
with TestClient(create_app(settings)) as c:
    assert c.get(f'/api/evidence/{evidence_id}').status_code == 401
    assert c.post('/api/auth/login', json={'key': key}).status_code == 200
    persisted = c.get(f'/api/jobs/{jid}').json()
    assert persisted['processed_frames'] == 36 and persisted['status'] == 'completed'
    assert c.get('/api/violations', params={'job_id': jid}).json()['total'] == len(records)
    assert c.get(f'/api/evidence/{evidence_id}').status_code == 200
with sqlite3.connect(settings.data_dir / 'trafficeye.sqlite3') as conn:
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
result.update({'private_media_authentication': 'passed', 'sqlite_persistence_after_application_restart': 'passed', 'sqlite_integrity': 'ok', 'all_values_are_synthetic_fixture_results_not_ml_accuracy': True})
print('RELEASE_SMOKE_JSON ' + json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--rebuild-frontend', action='store_true')
    args = parser.parse_args()
    archive = args.archive.resolve()
    verified = verify(archive)
    builds = []
    with tempfile.TemporaryDirectory(prefix='trafficeye-extracted-smoke-') as folder:
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder)  # entry paths, CRC and hashes already checked by verify()
        extracted = Path(folder) / 'TrafficEye-AI'
        if args.rebuild_frontend:
            npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
            if not npm:
                parser.error('Node/npm are required for --rebuild-frontend.')
            for command in ([npm,'ci','--no-audit','--no-fund'],[npm,'run','build']):
                run = subprocess.run(command, cwd=extracted / 'frontend', capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150)
                builds.append({'command': ['npm', *command[1:]], 'returncode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr})
                if run.returncode:
                    raise RuntimeError(run.stdout + run.stderr)
        env = {k:v for k,v in os.environ.items() if not k.startswith('TE_')}
        env.update({'PYTHONUTF8':'1', 'TE_DATA_DIR':str(extracted/'data'), 'TE_MODEL_DIR':str(extracted/'models'), 'TE_SAMPLE_DIR':str(extracted/'samples')})
        child = subprocess.run([sys.executable,'-c',PROBE],cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        if child.returncode:
            raise RuntimeError(child.stdout + child.stderr)
        line = next(line for line in child.stdout.splitlines() if line.startswith('RELEASE_SMOKE_JSON '))
        results = json.loads(line.removeprefix('RELEASE_SMOKE_JSON '))
    report = {'status':'passed','archive':archive.name,'sha256':verified['sha256'],'runtime_uses_extracted_source_and_clean_schema':True,'python_dependencies':'existing verified sandbox requirements, not a fresh isolated Python install','frontend_checks':builds,'api_smoke':results,'windows_runtime_tested':False,'cuda_tested':False,'trained_custom_model_accuracy_tested':False}
    text = json.dumps(report,indent=2)
    if args.output:
        args.output.write_text(text+'\n',encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
