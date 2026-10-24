"""BoT-SORT for real detections and a transparent, deterministic demo-only tracker."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import yaml

from .config import ROOT, VEHICLE_CLASSES
from .inference import Detection


def iou(a, b):
    intersection = max(0., min(a[2], b[2]) - max(a[0], b[0])) * max(0., min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0., a[2] - a[0]) * max(0., a[3] - a[1])
    area_b = max(0., b[2] - b[0]) * max(0., b[3] - b[1])
    return intersection / max(1., area_a + area_b - intersection)


class BoTSortTracker:
    def __init__(self, config):
        from ultralytics.trackers.bot_sort import BOTSORT
        args = yaml.safe_load((ROOT / "config" / "botsort.yaml").read_text())
        for key in ("track_high_thresh", "track_low_thresh", "new_track_thresh", "track_buffer", "match_thresh", "gmc_method"):
            args[key] = getattr(config, key)
        self.tracker = BOTSORT(SimpleNamespace(**args))

    def update(self, detections: list[Detection], frame):
        from ultralytics.engine.results import Boxes
        vehicles = [d for d in detections if d.class_name in VEHICLE_CLASSES]
        rows = np.asarray([[*d.bbox, d.confidence, VEHICLE_CLASSES.index(d.class_name)] for d in vehicles], dtype=np.float32).reshape(-1, 6)
        # BoT-SORT receives VEHICLES ONLY: helmets and belts do not become vehicle identities.
        boxes = Boxes(rows, frame.shape[:2]).numpy()
        output = self.tracker.update(boxes, frame)
        tracked = []
        for row in output:
            x1, y1, x2, y2, track_id, score, class_id = row[:7]
            if 0 <= int(class_id) < len(VEHICLE_CLASSES):
                tracked.append(Detection(VEHICLE_CLASSES[int(class_id)], float(score), [float(x1), float(y1), float(x2), float(y2)], int(track_id)))
        return tracked


class DemoTracker:
    """Class-aware greedy IoU/velocity recovery. This is NOT BoT-SORT or a claimed benchmark."""
    def __init__(self, config):
        self.config = config
        self.tracks = {}
        self.counter = 0
        self.tick = 0

    def update(self, detections, frame):
        self.tick += 1
        vehicles = [d for d in detections if d.class_name in VEHICLE_CLASSES and d.confidence >= self.config.confidence]
        self.tracks = {k: v for k, v in self.tracks.items() if self.tick - v["tick"] <= self.config.track_buffer}
        candidates = []
        for idx, det in enumerate(vehicles):
            for tid, old in self.tracks.items():
                if old["class"] != det.class_name:
                    continue
                gap = self.tick - old["tick"]
                predicted = [v + old["velocity"][i] * gap for i, v in enumerate(old["bbox"])]
                score = iou(predicted, det.bbox)
                if score > .15:
                    candidates.append((score, idx, tid))
        used_dets, used_tracks = set(), set()
        for _, idx, tid in sorted(candidates, reverse=True):
            if idx in used_dets or tid in used_tracks:
                continue
            vehicles[idx].track_id = tid
            used_dets.add(idx)
            used_tracks.add(tid)
        for det in vehicles:
            if det.track_id is None:
                self.counter += 1
                det.track_id = self.counter
            old = self.tracks.get(det.track_id)
            velocity = [(a - b) / max(1, self.tick - old["tick"]) for a, b in zip(det.bbox, old["bbox"])] if old else [0.] * 4
            self.tracks[det.track_id] = {"bbox": det.bbox, "velocity": velocity, "tick": self.tick, "class": det.class_name}
        return vehicles
