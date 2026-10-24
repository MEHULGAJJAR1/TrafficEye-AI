"""Original synthetic traffic fixture. All returned detections are scripted, NOT AI predictions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .inference import Detection

DEMO_NAME = "traffic_demo_60s.mp4"
MANIFEST_NAME = "demo_manifest.json"


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_manifest():
    classes = ["Bike", "Car", "Jeep", "Van"]
    actors = []
    for i in range(28):
        lane = i % 4
        name = classes[(i * 7 + i // 4) % 4]
        actors.append({"id": i + 1, "start": round(-5 + i * 2.2, 2), "travel": 8.4, "lane": lane, "class_name": name, "status": ("Helmet" if i % 3 == 0 else "No-Helmet") if name == "Bike" else ("No-Seatbelt" if i % 4 == 1 or i % 7 == 0 else "Seatbelt")})
    return {"schema": 1, "kind": "scripted-synthetic-demo-not-ai", "license": "CC0-1.0", "width": 960, "height": 540, "fps": 12, "duration": 60, "actors": actors}


def scene_objects(manifest, timestamp):
    w, h = manifest["width"], manifest["height"]
    result = []
    for actor in manifest["actors"]:
        phase = (timestamp - actor["start"]) / actor["travel"]
        if not 0 <= phase <= 1:
            continue
        name = actor["class_name"]
        bw = 28 if name == "Bike" else 54 if name == "Car" else 62
        bh = 60 if name == "Bike" else 94 if name != "Van" else 112
        x = [.245, .41, .59, .755][actor["lane"]] * w
        y = -bh + phase * (h + 2 * bh)
        if actor["lane"] >= 2:
            y = h - y
        raw = [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2]
        if raw[3] < 8 or raw[1] > h - 8:
            continue
        bbox = [max(0., raw[0]), max(0., raw[1]), min(w - 1., raw[2]), min(h - 1., raw[3])]
        if name == "Bike":
            aux = [x - 10, y - bh * .37 - 10, x + 10, y - bh * .37 + 10]
        else:
            aux = [x - bw * .26, y - bh * .3, x + bw * .10, y - bh * .02]
        aux_visible = aux[1] >= 0 and aux[3] < h
        result.append((actor, raw, Detection(name, .91 + actor["id"] % 5 * .01, bbox), Detection(actor["status"], .87 + actor["id"] % 6 * .01, aux) if aux_visible else None))
    return result


class DemoDetector:
    def __init__(self, sample_dir):
        self.manifest = json.loads((sample_dir / MANIFEST_NAME).read_text())
        if self.manifest.get("kind") != "scripted-synthetic-demo-not-ai":
            raise ValueError("Invalid demo manifest.")

    def predict(self, frame, config, timestamp):
        detections = []
        for _, _, vehicle, safety in scene_objects(self.manifest, timestamp):
            detections.append(vehicle)
            if safety:
                detections.append(safety)
        return detections, 0.0  # No model inference occurred; inference FPS is intentionally zero.


def render_scene(manifest, timestamp):
    w, h = manifest["width"], manifest["height"]
    image = np.full((h, w, 3), (25, 32, 37), np.uint8)
    cv2.rectangle(image, (125, 0), (835, h), (43, 48, 56), -1)
    cv2.rectangle(image, (105, 0), (122, h), (62, 95, 93), -1)
    cv2.rectangle(image, (838, 0), (855, h), (62, 95, 93), -1)
    cv2.line(image, (480, 0), (480, h), (66, 191, 221), 3)
    cv2.line(image, (487, 0), (487, h), (66, 191, 221), 2)
    for x in (315, 645):
        for y in range(-50, h + 50, 65):
            cv2.line(image, (x, y), (x, y + 32), (127, 132, 135), 2)
    # Road markings are part of the original synthetic drawing, not evidence overlays.
    cv2.putText(image, "IN", (158, 280), cv2.FONT_HERSHEY_SIMPLEX, .65, (91, 112, 120), 2)
    cv2.putText(image, "OUT", (770, 280), cv2.FONT_HERSHEY_SIMPLEX, .65, (91, 112, 120), 2)
    palette = [(179, 169, 53), (209, 129, 66), (125, 110, 208), (153, 167, 181), (89, 160, 208)]
    for actor, bbox, vehicle, safety in scene_objects(manifest, timestamp):
        x1, y1, x2, y2 = map(int, bbox)
        color = palette[actor["id"] % len(palette)]
        cx = (x1 + x2) // 2
        if actor["class_name"] == "Bike":
            cv2.line(image, (cx, y1), (cx, y2), (12, 16, 22), 8)
            cv2.rectangle(image, (x1, y1 + 15), (x2, y2 - 10), color, -1)
        else:
            cv2.rectangle(image, (x1 - 4, y1 + 10), (x2 + 4, y2 - 10), (15, 18, 23), -1)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(image, (x1 + 5, y1 + 13), (x2 - 5, y1 + 35), (58, 68, 74), -1)
            cv2.rectangle(image, (x1 + 5, y2 - 23), (x2 - 5, y2 - 9), (58, 68, 74), -1)
            cv2.line(image, (x1 + 5, y1 + 3), (x2 - 5, y1 + 3), (215, 230, 232), 3)
        if safety:
            a, b, c, d = map(int, safety.bbox)
            if actor["class_name"] == "Bike":
                cv2.circle(image, ((a + c) // 2, (b + d) // 2), 9, (110, 181, 224) if actor["status"] == "No-Helmet" else (224, 228, 227), -1)
            elif actor["status"] == "Seatbelt":
                cv2.line(image, (a + 2, b + 2), (c - 2, d - 2), (60, 220, 167), 3)
    cv2.rectangle(image, (0, 0), (w, 38), (16, 22, 29), -1)
    cv2.putText(image, "TRAFFICEYE  /  SYNTHETIC SCENARIO - NOT CAMERA FOOTAGE", (18, 25), cv2.FONT_HERSHEY_SIMPLEX, .55, (170, 215, 230), 1, cv2.LINE_AA)
    cv2.rectangle(image, (0, h - 30), (w, h), (16, 22, 29), -1)
    cv2.putText(image, f"CC0 original fixture  |  {timestamp:05.1f}s  |  Scripted objects, not AI predictions", (18, h - 10), cv2.FONT_HERSHEY_SIMPLEX, .46, (152, 168, 177), 1, cv2.LINE_AA)
    return image


def prepare_sample(destination: Path):
    import imageio_ffmpeg
    destination.mkdir(parents=True, exist_ok=True)
    manifest = fixture_manifest()
    path = destination / DEMO_NAME
    writer = imageio_ffmpeg.write_frames(str(path), (manifest["width"], manifest["height"]), fps=manifest["fps"], codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p", quality=7, macro_block_size=2, output_params=["-movflags", "+faststart"], ffmpeg_log_level="error")
    writer.send(None)
    try:
        for i in range(int(manifest["duration"] * manifest["fps"])):
            writer.send(cv2.cvtColor(render_scene(manifest, i / manifest["fps"]), cv2.COLOR_BGR2RGB))
    finally:
        writer.close()
    manifest["sha256"] = sha256(path)
    (destination / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
