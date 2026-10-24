"""Conservative spatial association + time-window voting, not an enforcement-grade adjudicator."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot

import cv2
import numpy as np

from .tracking import iou


@dataclass
class TrackState:
    votes: dict = field(default_factory=dict)
    recorded: set = field(default_factory=set)
    vote_spans: dict = field(default_factory=dict)
    side: int | None = None
    point: tuple | None = None
    counted: set = field(default_factory=set)
    last_time: float = 0


def intersection_over_object(obj, roi):
    area = max(1., (obj[2] - obj[0]) * (obj[3] - obj[1]))
    overlap = max(0., min(obj[2], roi[2]) - max(obj[0], roi[0])) * max(0., min(obj[3], roi[3]) - max(obj[1], roi[1]))
    return overlap / area


class ViolationEngine:
    def __init__(self, config):
        self.config = config
        self.states: dict[int, TrackState] = {}
        self.recent: deque = deque()

    def zone(self, bbox, width, height):
        point = ((bbox[0] + bbox[2]) / (2 * width), min(1., bbox[3] / height))
        for zone in self.config.zones:
            polygon = np.asarray(zone.polygon, dtype=np.float32)
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return zone.name
        return "outside"

    def roi(self, vehicle, kind):
        x1, y1, x2, y2 = vehicle.bbox
        w, h = x2 - x1, y2 - y1
        if kind == "helmet":
            return [x1 - .12 * w, y1 - self.config.bike_top_margin * h, x2 + .12 * w, y2]
        # Front cabin heuristic. Without a driver annotation/keypoint model, driver identity
        # cannot be guaranteed; ambiguous overlapping cabins are deliberately rejected.
        return [x1 - .03 * w, y1 - .03 * h, x2 + .03 * w, y1 + .68 * h]

    def associate(self, vehicles, objects):
        associations = {}
        for obj in objects:
            if obj.class_name not in ("Helmet", "No-Helmet", "Seatbelt", "No-Seatbelt") or obj.confidence < self.config.violation_confidence:
                continue
            kind = "helmet" if "Helmet" in obj.class_name else "seatbelt"
            candidates = []
            cx, cy = (obj.bbox[0] + obj.bbox[2]) / 2, (obj.bbox[1] + obj.bbox[3]) / 2
            for vehicle in vehicles:
                if (kind == "helmet") != (vehicle.class_name == "Bike"):
                    continue
                if min(vehicle.bbox[2] - vehicle.bbox[0], vehicle.bbox[3] - vehicle.bbox[1]) < self.config.min_vehicle_pixels:
                    continue
                region = self.roi(vehicle, kind)
                if not (region[0] <= cx <= region[2] and region[1] <= cy <= region[3]):
                    continue
                score = intersection_over_object(obj.bbox, region)
                if score >= self.config.association_overlap:
                    candidates.append((score, vehicle.track_id))
            candidates.sort(reverse=True)
            if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < self.config.ambiguity_margin):
                continue
            key = (candidates[0][1], kind)
            associations.setdefault(key, []).append(obj)
        resolved = {}
        for key, candidates in associations.items():
            candidates.sort(key=lambda d: d.confidence, reverse=True)
            best = candidates[0]
            opposite = next((d for d in candidates[1:] if d.class_name != best.class_name), None)
            if opposite is not None and best.confidence - opposite.confidence < self.config.ambiguity_margin:
                continue  # conflicting compliance evidence is unknown, never a forced violation
            resolved[key] = best
        return resolved

    def crossing(self, state, vehicle, width, height, zone):
        if zone == "outside":
            state.side = None
            state.point = None
            return None
        point = ((vehicle.bbox[0] + vehicle.bbox[2]) / (2 * width), vehicle.bbox[3] / height)
        a, b = self.config.count_line
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dy)
        signed = (dx * (point[1] - a[1]) - dy * (point[0] - a[0])) / length
        side = 1 if signed > self.config.line_hysteresis else -1 if signed < -self.config.line_hysteresis else None
        if side is None:
            return None
        previous, previous_point = state.side, state.point
        state.side, state.point = side, point
        if previous is None or previous == side:
            return None
        # Check intersection with the FINITE line, not its infinite extension.
        pdx, pdy = point[0] - previous_point[0], point[1] - previous_point[1]
        denominator = pdx * dy - pdy * dx
        if abs(denominator) < 1e-9:
            return None
        t = ((a[0] - previous_point[0]) * dy - (a[1] - previous_point[1]) * dx) / denominator
        u = ((a[0] - previous_point[0]) * pdy - (a[1] - previous_point[1]) * pdx) / denominator
        if not (0 <= t <= 1 and 0 <= u <= 1):
            return None
        direction = self.config.positive_direction if previous < side else ("OUT" if self.config.positive_direction == "IN" else "IN")
        if direction in state.counted:
            return None
        state.counted.add(direction)
        return {"track_id": vehicle.track_id, "direction": direction}

    def update(self, vehicles, detections, width, height, timestamp):
        cfg = self.config
        # Bound memory for long recordings; tracker IDs are never recycled within a job.
        self.states = {k: v for k, v in self.states.items() if timestamp - v.last_time < 120}
        self.recent = deque(v for v in self.recent if timestamp - v[0] <= cfg.duplicate_seconds)
        associations = self.associate(vehicles, detections)
        records, enriched, crossings = [], [], []
        for vehicle in vehicles:
            if vehicle.track_id is None or vehicle.confidence < cfg.confidence:
                continue
            state = self.states.setdefault(vehicle.track_id, TrackState())
            if timestamp - state.last_time > 2:
                state.votes.clear()
                state.vote_spans.clear()
                state.side = None
            state.last_time = timestamp
            zone = self.zone(vehicle.bbox, width, height)
            row = {**vehicle.json(), "zone": zone, "helmet_status": "not-applicable" if vehicle.class_name != "Bike" else "unknown", "seatbelt_status": "not-applicable" if vehicle.class_name == "Bike" else "unknown"}
            cross = self.crossing(state, vehicle, width, height, zone)
            if cross:
                crossings.append(cross)
            kind = "helmet" if vehicle.class_name == "Bike" else "seatbelt"
            history = state.votes.setdefault(kind, deque(maxlen=cfg.vote_window))
            obj = associations.get((vehicle.track_id, kind)) if zone != "outside" else None
            history.append((timestamp, obj))
            previous = state.vote_spans.get(kind)
            label = obj.class_name if obj is not None else (previous[0] if previous else None)
            same = [(t, o) for t, o in history if o is not None and o.class_name == label]
            supported = len(same) >= cfg.min_votes and len(same) / len(history) >= cfg.vote_ratio
            since = timestamp
            if supported:
                # Maturity carries across consecutive qualifying rolling windows. Limiting
                # the span to seven frames would make .25 s impossible at 25+ FPS.
                since = previous[1] if previous and previous[0] == label else same[0][0]
                state.vote_spans[kind] = (label, since)
            else:
                state.vote_spans.pop(kind, None)
            if obj is not None:
                sufficient = supported and timestamp - since + 1e-9 >= cfg.min_evidence_seconds
                if sufficient:
                    row[kind + "_status"] = obj.class_name
                    violation = obj.class_name.startswith("No-")
                    if violation and obj.class_name not in state.recorded:
                        duplicate = any(other_type == obj.class_name and other_id != vehicle.track_id and iou(other_box, vehicle.bbox) >= cfg.duplicate_iou for _, other_id, other_type, other_box in self.recent)
                        state.recorded.add(obj.class_name)
                        if not duplicate:
                            self.recent.append((timestamp, vehicle.track_id, obj.class_name, vehicle.bbox))
                            records.append({"track_id": vehicle.track_id, "vehicle_class": vehicle.class_name, "violation_type": obj.class_name, "helmet_status": row["helmet_status"], "seatbelt_status": row["seatbelt_status"], "confidence": round(sum(o.confidence for _, o in same) / len(same), 4), "zone": zone, "vehicle_bbox": vehicle.bbox, "object_bbox": obj.bbox, "votes": len(same)})
                else:
                    row[kind + "_status"] = "unconfirmed"
            enriched.append(row)
        return enriched, records, crossings
