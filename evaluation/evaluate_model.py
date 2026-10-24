"""Run genuine Ultralytics validation on a user-supplied labelled dataset. Never emits invented metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import RuntimeConfig
from backend.app.inference import map_classes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, required=True, help='Trusted custom YOLO26 .pt checkpoint.')
    parser.add_argument('--data', type=Path, required=True, help='Trusted YOLO dataset YAML containing an annotated val split.')
    parser.add_argument('--output', type=Path, default=ROOT / 'evaluation' / 'results' / 'detection')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=4)
    args = parser.parse_args()
    if not args.weights.is_file() or args.weights.suffix.lower() != '.pt':
        parser.error('--weights must be an existing trusted .pt checkpoint.')
    if not args.data.is_file() or args.data.suffix.lower() not in ('.yaml', '.yml'):
        parser.error('--data must be an existing trusted labelled dataset YAML.')
    if args.batch < 1 or args.batch > 64:
        parser.error('--batch must be between 1 and 64.')
    RuntimeConfig(imgsz=args.imgsz)
    import torch
    from ultralytics import YOLO
    model = YOLO(str(args.weights))
    mapped, missing = map_classes(model.names)
    if missing or model.task != 'detect':
        parser.error('Model schema incompatible; missing classes: ' + ', '.join(missing))
    if args.device != 'cpu' and not torch.cuda.is_available() and args.device != 'mps':
        print('CUDA is unavailable; evaluating on CPU.')
        args.device = 'cpu'
    args.output.mkdir(parents=True, exist_ok=True)
    # Ultralytics creates confusion_matrix.png, confusion_matrix_normalized.png, curves
    # and annotation artifacts. A suitable dataset, including negative samples, is required.
    from ultralytics.models.yolo.detect.val import DetectionValidator
    captured = {}
    class ReportingValidator(DetectionValidator):
        def __init__(self, *values, **kwargs):
            super().__init__(*values, **kwargs)
            captured['instance'] = self
    # YOLO.val() does not retain its validator on the model in this pinned release.
    # The documented custom-validator hook gives us the actual confusion matrix.
    metrics = model.val(validator=ReportingValidator, data=str(args.data.resolve()), imgsz=args.imgsz, batch=args.batch, device=args.device, plots=True, save_json=False, project=str(args.output.resolve()), name='validation', exist_ok=True, verbose=True)
    matrix = captured['instance'].confusion_matrix
    matrix_array = matrix.matrix
    speed = {k: float(v) for k, v in metrics.speed.items()}
    inference_ms = speed.get('inference', 0)
    output = {
        'scope': 'actual labelled validation split, not demo observations',
        'weights': str(args.weights.resolve()), 'dataset': str(args.data.resolve()),
        'device': args.device, 'image_size': args.imgsz, 'batch': args.batch,
        'precision': float(metrics.box.mp), 'recall': float(metrics.box.mr),
        'mAP@0.5': float(metrics.box.map50), 'mAP@0.5:0.95': float(metrics.box.map),
        'per_class': metrics.summary(normalize=True, decimals=6),
        'confusion_matrix': matrix_array.tolist() if matrix_array is not None else None,
        'confusion_matrix_axis_labels': [model.names[k] for k in sorted(model.names)] + ['background'],
        'confusion_matrix_orientation': 'rows=predicted, columns=true; final row/column is background',
        'speed_ms_per_image': speed,
        'inference_fps_equivalent': 1000 / inference_ms if inference_ms > 0 else None,
        'notes': ['Detection metrics do not measure tracking or violation-association accuracy.', 'FPS depends on hardware, batch, warmup, image size and data; compare equivalent settings only.', 'Review per-class sample counts and the confusion matrix before interpreting aggregate mAP.'],
    }
    path = args.output / 'metrics.json'
    def json_ready(value):
        import math
        import numpy as np
        if isinstance(value, dict):
            return {str(k): json_ready(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_ready(v) for v in value]
        if isinstance(value, np.ndarray):
            return json_ready(value.tolist())
        if isinstance(value, np.generic):
            return json_ready(value.item())
        if isinstance(value, float) and not math.isfinite(value):
            return None  # undefined metric is unavailable, not fabricated as a number
        return value
    path.write_text(json.dumps(json_ready(output), indent=2, allow_nan=False), encoding='utf-8')
    print(f'Actual validation results: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
