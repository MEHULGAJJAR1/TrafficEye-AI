"""Real network protocol tests, NOT trained-model accuracy claims."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from backend.app.config import REQUIRED_CLASSES, ROOT, RuntimeConfig
from backend.app.inference import ModelService, ModelUnavailable


def test_missing_weights_fail_clearly(settings):
    service = ModelService(settings)
    with pytest.raises(ModelUnavailable, match='missing'):
        service.load(RuntimeConfig())
    assert not service.status(RuntimeConfig())['ready']


@pytest.fixture(scope='module')
def untrained_protocol_weights(tmp_path_factory):
    """Initialize an eight-class YOLO26 network from packaged architecture; no downloads/training."""
    import torch
    import ultralytics
    from ultralytics import YOLO
    torch.set_num_threads(2)
    torch.manual_seed(1)
    root = tmp_path_factory.mktemp('untrained-yolo26-protocol')
    architecture = Path(ultralytics.__file__).parent / 'cfg/models/26/yolo26.yaml'
    config = yaml.safe_load(architecture.read_text())
    config['nc'] = 8
    config['scale'] = 'n'
    path = root / 'protocol-yolo26n.yaml'
    path.write_text(yaml.safe_dump(config))
    model = YOLO(str(path), task='detect')
    model.model.names = dict(enumerate(REQUIRED_CLASSES))
    checkpoint = root / 'protocol.pt'
    model.save(str(checkpoint))
    return checkpoint


def test_real_cpu_prediction_protocol_with_untrained_eight_class_network(settings, untrained_protocol_weights):
    settings.prepare()
    shutil.copy2(untrained_protocol_weights, settings.model_dir / 'traffic-custom.pt')
    service = ModelService(settings)
    config = RuntimeConfig(imgsz=320, device='cpu')
    service.load(config)
    assert service.status(config)['ready']
    detections, milliseconds = service.predict(np.zeros((240,320,3), np.uint8), config)
    assert milliseconds > 0
    assert isinstance(detections, list)
    assert all(d.class_name in REQUIRED_CLASSES for d in detections)
    # Random/untrained network outputs are not shipped or treated as accuracy evidence.


def test_model_evaluation_exports_matrix_and_per_class_protocol(tmp_path, untrained_protocol_weights):
    """Run actual validation on an ORIGINAL synthetic label fixture to test report plumbing only."""
    images, labels = tmp_path / 'images/val', tmp_path / 'labels/val'
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    for i in range(8):
        image = np.zeros((320,320,3), np.uint8)
        cv2.rectangle(image, (100,100), (200,220), (70,160,180), -1)
        cv2.imwrite(str(images / f'fixture{i}.jpg'), image)
        (labels / f'fixture{i}.txt').write_text(f'{i} .46875 .5 .3125 .375\n')
    data = tmp_path / 'fixture.yaml'
    data.write_text(yaml.safe_dump({'path': str(tmp_path), 'train': 'images/val', 'val': 'images/val', 'names': dict(enumerate(REQUIRED_CLASSES))}))
    output = tmp_path / 'results'
    result = subprocess.run([sys.executable, str(ROOT / 'evaluation/evaluate_model.py'), '--weights', str(untrained_protocol_weights), '--data', str(data), '--output', str(output), '--imgsz', '320', '--batch', '2', '--device', 'cpu'], capture_output=True, text=True, timeout=90, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    metrics = json.loads((output / 'metrics.json').read_text())
    assert len(metrics['confusion_matrix']) == 9
    assert len(metrics['confusion_matrix'][0]) == 9
    assert len(metrics['per_class']) == 8
    assert {'precision', 'recall', 'mAP@0.5', 'mAP@0.5:0.95'} <= metrics.keys()
    assert (output / 'validation/confusion_matrix.png').is_file()


@pytest.mark.inference
def test_optional_official_coco_weights_are_rejected_as_safety_model(settings):
    path = os.environ.get('TE_TEST_COCO_WEIGHTS')
    if not path:
        pytest.skip('Set TE_TEST_COCO_WEIGHTS to trusted official local yolo26n.pt weights to run this optional compatibility test.')
    settings.prepare()
    shutil.copy2(path, settings.model_dir / 'traffic-custom.pt')
    service = ModelService(settings)
    with pytest.raises(ModelUnavailable, match='Missing required classes'):
        service.load(RuntimeConfig())
    status = service.status(RuntimeConfig())
    assert not status['ready'] and 'No-Seatbelt' in status['missing_classes']


def test_real_job_pipeline_executes_with_untrained_protocol_weights(client, tmp_path, untrained_protocol_weights):
    """Exercises actual PyTorch→BoT-SORT→SQLite code; NOT a trained safety-model validation."""
    from conftest import wait_job
    settings = client.app.state.settings
    shutil.copy2(untrained_protocol_weights, settings.model_dir / 'traffic-custom.pt')
    config = client.get('/api/config').json()
    config['imgsz'] = 320
    config['device'] = 'cpu'
    config['gmc_method'] = 'none'
    assert client.put('/api/config', json=config).status_code == 200
    source = tmp_path / 'protocol.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 12, (320, 240))
    for _ in range(12):
        writer.write(np.zeros((240, 320, 3), np.uint8))
    writer.release()
    with source.open('rb') as file:
        result = client.post('/api/uploads', files={'file': ('protocol.avi', file)})
    assert result.status_code == 201
    job = result.json()
    start = client.post(f"/api/jobs/{job['id']}/start", json={'mode': 'real', 'max_seconds': None})
    assert start.status_code == 200, start.text
    completed = wait_job(client, job['id'])
    assert completed['status'] == 'completed', completed
    assert completed['mode'] == 'real' and completed['processed_frames'] == 12
    assert completed['inference_fps'] > 0
    assert completed['last_result']['inference_ms'] > 0
    assert all(d['class_name'] in REQUIRED_CLASSES for d in completed['last_result']['detections'])
    assert client.get('/api/reports.csv', params={'job_id': job['id']}).status_code == 200


def test_model_configuration_cli_preserves_saved_selection_on_failure(settings, tmp_path, untrained_protocol_weights):
    """The CLI accepts a protocol fixture; failed candidates cannot replace working settings."""
    from backend.app.config import ConfigStore
    settings.prepare()
    env = {**os.environ, 'TE_DATA_DIR': str(settings.data_dir), 'TE_MODEL_DIR': str(settings.model_dir)}

    def run(*args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/configure_model.py'), *map(str, args)], capture_output=True, text=True, timeout=40, cwd=ROOT, env=env)

    accepted = run('--weights', untrained_protocol_weights, '--name', 'protocol.pt')
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert 'does NOT certify model accuracy' in accepted.stdout
    assert ConfigStore(settings.data_dir).get().model_file == 'protocol.pt'
    overwrite = run('--weights', untrained_protocol_weights, '--name', 'protocol.pt')
    assert overwrite.returncode == 2 and 'already exists' in overwrite.stderr
    invalid = tmp_path / 'invalid.pt'
    invalid.write_bytes(b'not a checkpoint')
    rejected = run('--weights', invalid, '--name', 'invalid.pt')
    assert rejected.returncode == 2 and 'MODEL NOT READY' in rejected.stdout
    assert ConfigStore(settings.data_dir).get().model_file == 'protocol.pt'
    bad_name = run('--weights', untrained_protocol_weights, '--name', '../escape.pt')
    assert bad_name.returncode == 2 and 'simple local .pt filename' in bad_name.stderr
    assert not (settings.model_dir.parent / 'escape.pt').exists()
    inspected = run()
    assert inspected.returncode == 0 and '"ready": true' in inspected.stdout
