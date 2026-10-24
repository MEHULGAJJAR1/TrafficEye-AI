"""Trusted local YOLO26 weights only. No automatic weights download or invented predictions."""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import yaml

from .config import REQUIRED_CLASSES, ROOT, VEHICLE_CLASSES


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: list[float]
    track_id: int | None = None

    def json(self):
        return asdict(self)


def normalized_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def map_classes(names, aliases_path: Path | None = None):
    aliases = yaml.safe_load((aliases_path or ROOT / "config" / "class_aliases.yaml").read_text(encoding="utf-8"))
    lookup = {normalized_name(alias): canonical for canonical, variants in aliases.items() for alias in [canonical, *variants]}
    names = dict(enumerate(names)) if isinstance(names, (list, tuple)) else names
    if not isinstance(names, dict) or len(names) > 5000:
        raise ValueError("Model class names must be a bounded mapping or list.")
    mapped = {int(i): lookup[normalized_name(v)] for i, v in names.items() if normalized_name(v) in lookup}
    missing = [name for name in REQUIRED_CLASSES if name not in mapped.values()]
    return mapped, missing


class ModelUnavailable(RuntimeError):
    pass


class ModelService:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.model = None
        self.signature = None
        self.mapping = {}
        self.validation = {"state": "not_validated", "ready": False, "message": "Place trusted, custom-trained YOLO26 .pt weights in models/ and validate the model.", "required_classes": list(REQUIRED_CLASSES)}
        self.device = "cpu"

    def status(self, config):
        path = self.settings.model_dir / config.model_file
        if not path.is_file():
            return {"state": "missing", "ready": False, "message": f"Missing models/{config.model_file}. Demo is available; real violation detection requires all eight custom classes.", "required_classes": list(REQUIRED_CLASSES), "file": config.model_file}
        # Do not report a previously validated DIFFERENT model as ready.
        sig = (str(path), path.stat().st_mtime_ns, path.stat().st_size, config.device)
        if sig != self.signature:
            return {"state": "not_validated", "ready": False, "file": config.model_file, "message": "Weights found. Validate their class mapping before running real inference.", "required_classes": list(REQUIRED_CLASSES)}
        return dict(self.validation)

    def load(self, config):
        path = self.settings.model_dir / config.model_file
        if not path.is_file():
            raise ModelUnavailable(f"Custom model missing: models/{config.model_file}. Add trusted weights, then validate in Settings. Demo mode does not require weights.")
        # Restrict the editable configuration to a filename within models; reject symlink escapes too.
        if not path.resolve().is_relative_to(self.settings.model_dir.resolve()):
            raise ModelUnavailable("The model must be inside the configured models directory.")
        sig = (str(path), path.stat().st_mtime_ns, path.stat().st_size, config.device)
        with self.lock:
            if self.signature == sig and self.validation.get("ready"):
                return self.model
            try:
                import torch
                from ultralytics import YOLO
                torch.set_num_threads(self.settings.torch_threads)
                requested = config.device
                if requested == "auto":
                    requested = "cuda:0" if torch.cuda.is_available() else "cpu"
                if (requested.startswith("cuda") or requested.isdigit()) and not torch.cuda.is_available():
                    requested = "cpu"
                if requested == "mps" and not torch.backends.mps.is_available():
                    requested = "cpu"
                model = YOLO(str(path), task="detect")
                if model.task != "detect":
                    raise ModelUnavailable("Only axis-aligned object detection models are supported.")
                mapped, missing = map_classes(model.names)
                self.signature = sig
                self.validation = {"state": "incompatible" if missing else "ready", "ready": not missing, "file": config.model_file, "required_classes": list(REQUIRED_CLASSES), "model_names": {str(k): str(v) for k, v in model.names.items()}, "mapping": mapped, "missing_classes": missing, "device": requested, "message": "Missing required classes: " + ", ".join(missing) if missing else "All required class names are present. This validates the schema, NOT detection accuracy or training provenance."}
                self.model, self.mapping, self.device = model, mapped, requested
                if missing:
                    raise ModelUnavailable(self.validation["message"])
                return model
            except ModelUnavailable:
                raise
            except Exception as exc:
                self.model = None
                self.signature = None
                self.validation = {"state": "error", "ready": False, "message": f"Model load failed ({type(exc).__name__}). Check trusted weights, Ultralytics and PyTorch compatibility."}
                raise ModelUnavailable(self.validation["message"]) from exc

    def predict(self, frame, config):
        with self.lock:
            model = self.load(config)
            started = time.perf_counter()
            result = model.predict(frame, imgsz=config.imgsz, conf=min(config.confidence, config.track_low_thresh), iou=config.iou, device=self.device, verbose=False, half=False, max_det=300)[0]
            ms = (time.perf_counter() - started) * 1000
            h, w = frame.shape[:2]
            detections = []
            if result.boxes is not None:
                for box in result.boxes.cpu().numpy().data:
                    x1, y1, x2, y2, conf, class_id = map(float, box[:6])
                    name = self.mapping.get(int(class_id))
                    if name is None or not all(math.isfinite(v) for v in (x1, y1, x2, y2, conf)):
                        continue
                    bbox = [max(0., min(w - 1., x1)), max(0., min(h - 1., y1)), max(0., min(w - 1., x2)), max(0., min(h - 1., y2))]
                    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                        continue
                    if name not in VEHICLE_CLASSES and conf < config.confidence:
                        continue
                    detections.append(Detection(name, round(conf, 4), bbox))
            return detections, ms
