"""Bounded single-inference-worker job orchestration. No video is loaded into memory."""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2

from .association import ViolationEngine
from .database import utcnow
from .demo import DEMO_NAME, MANIFEST_NAME, DemoDetector, sha256
from .security import inside
from .tracking import BoTSortTracker, DemoTracker, iou
from .video import transcode_preview

log = logging.getLogger("trafficeye.processing")
TERMINAL = {"completed", "cancelled", "failed", "interrupted"}


class JobConflict(ValueError):
    pass


@dataclass
class Control:
    gate: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self):
        self.gate.set()


def annotate(frame, tracks, detections, config, mode, video_time):
    image = frame.copy()
    h, w = image.shape[:2]
    for zone in config.zones:
        import numpy as np
        points = np.asarray([[int(x * w), int(y * h)] for x, y in zone.polygon], dtype=np.int32)
        cv2.polylines(image, [points], True, (103, 138, 93), 1)
    a, b = config.count_line
    cv2.line(image, (int(a[0] * w), int(a[1] * h)), (int(b[0] * w), int(b[1] * h)), (95, 215, 209), 2)
    for det in detections:
        if det.class_name not in ("Helmet", "No-Helmet", "Seatbelt", "No-Seatbelt"):
            continue
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        color = (94, 118, 249) if det.class_name.startswith("No-") else (155, 208, 79)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, f"{det.class_name} {det.confidence:.0%}", (max(0, x1), max(44, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .38, color, 1, cv2.LINE_AA)
    for track in tracks:
        x1, y1, x2, y2 = [int(v) for v in track["bbox"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), (181, 214, 53), 2)
        cv2.putText(image, f"#{track['track_id']} {track['class_name']} {track['confidence']:.0%}", (max(0, x1), max(48, y2 + 14)), cv2.FONT_HERSHEY_SIMPLEX, .4, (204, 232, 159), 1, cv2.LINE_AA)
    cv2.rectangle(image, (0, 0), (w, 32), (18, 23, 30), -1)
    label = "DEMO - SCRIPTED DATA, NOT AI" if mode == "demo" else "AI INFERENCE - HUMAN REVIEW REQUIRED"
    cv2.putText(image, f"{label} | {video_time:.2f}s", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (119, 206, 244), 1, cv2.LINE_AA)
    return image


def write_jpeg(path: Path, image):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 86])
    if not ok:
        raise RuntimeError("JPEG evidence encoding failed.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data.tobytes())
    os.replace(tmp, path)


class JobManager:
    def __init__(self, settings, db, configs, model, hub):
        self.settings, self.db, self.configs, self.model, self.hub = settings, db, configs, model, hub
        self.lock = threading.RLock()
        self.controls: dict[str, Control] = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")
        self.closing = False
        self.sample_hash = None
        manifest = settings.sample_dir / MANIFEST_NAME
        sample = settings.sample_dir / DEMO_NAME
        if manifest.exists() and sample.exists():
            try:
                fixture = json.loads(manifest.read_text())
                expected = fixture.get("sha256")
                if fixture.get("kind") == "scripted-synthetic-demo-not-ai" and expected and sha256(sample) == expected:
                    self.sample_hash = expected
            except (OSError, ValueError, AttributeError):
                log.warning("Synthetic sample manifest is unreadable. Run python scripts/prepare_sample.py --force; real model processing remains available.")
        self.db.recover()
        self.cleanup_orphans()
        for job in self.db.query("SELECT * FROM jobs WHERE preview_status='pending'"):
            self.prepare_preview(job["id"])

    def cleanup_orphans(self):
        """Recover files left by a killed upload/checkpoint; run before worker submission.

        This application is deliberately single-process. Do not share data/ between workers.
        """
        root = self.settings.data_dir
        jobs = self.db.query("SELECT id,source_path,preview_path FROM jobs")
        owned = {j['source_path'] for j in jobs} | {j['preview_path'] for j in jobs if j['preview_path']}
        evidence = {r['evidence_filename'] for r in self.db.query("SELECT evidence_filename FROM violations")}
        ids = {j['id'] for j in jobs}
        candidates = list(root.glob('settings.tmp'))
        for directory in ('uploads', 'previews', 'frames', 'evidence'):
            for path in (root / directory).rglob('*'):
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                unowned = directory in ('uploads', 'previews') and relative not in owned
                unowned |= directory == 'frames' and path.stem not in ids
                unowned |= directory == 'evidence' and path.relative_to(root / 'evidence').as_posix() not in evidence
                if path.suffix == '.tmp' or unowned:
                    candidates.append(path)
        for path in candidates:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning('Could not remove an orphan runtime file: %s', path.name)

    def publish(self, job_id):
        self.hub.publish(job_id)

    def is_demo(self, path):
        return bool(self.sample_hash and sha256(path) == self.sample_hash)

    def prepare_preview(self, job_id):
        job = self.db.job(job_id)
        if job["codec"].lower() in ("avc1", "h264", "avc3") and Path(job["source_path"]).suffix.lower() == ".mp4":
            self.db.update_job(job_id, preview_status="ready", preview_path=job["source_path"])
            return
        self.db.update_job(job_id, preview_status="preparing")
        self.preview_pool.submit(self._preview, job_id)

    def _preview(self, job_id):
        output = self.settings.data_dir / "previews" / f"{job_id}.mp4"
        try:
            job = self.db.job(job_id)
            transcode_preview(inside(self.settings.data_dir, job["source_path"]), output, self.settings.max_video_seconds)
            self.db.update_job(job_id, preview_status="ready", preview_path=f"previews/{job_id}.mp4")
            self.db.event(job_id, "preview", "Browser-compatible H.264 preview is ready.")
        except Exception:
            log.exception("Preview generation failed for job %s", job_id)
            self.db.update_job(job_id, preview_status="failed")
            self.db.event(job_id, "preview", "Preview conversion failed; backend processing can still use the original video.", "warning")
        self.publish(job_id)

    def start(self, job_id, options, retry=False):
        with self.lock:
            job = self.db.job(job_id)
            if job is None:
                raise KeyError(job_id)
            allowed = TERMINAL if retry else {"uploaded"}
            if job["status"] not in allowed or job_id in self.controls:
                raise JobConflict(f"Cannot {'retry' if retry else 'start'} a {job['status']} job.")
            if self.closing or len(self.controls) >= self.settings.max_queued_jobs + 1:
                raise JobConflict("The processing queue is full. Cancel a job or wait for completion.")
            config = self.configs.get()
            if options.mode == "demo":
                if not job["is_demo_source"] or not self.is_demo(inside(self.settings.data_dir, job["source_path"])):
                    raise JobConflict("Demo data is only valid for the included synthetic sample. It cannot be applied to arbitrary footage.")
            else:
                self.model.load(config)  # fail before queueing an impossible real-inference job
            if retry:
                self.db.clear_results(job_id)
                shutil.rmtree(self.settings.data_dir / "evidence" / job_id, ignore_errors=True)
                (self.settings.data_dir / "frames" / f"{job_id}.jpg").unlink(missing_ok=True)
            control = Control()
            self.controls[job_id] = control
            target_seconds = min(job["duration"], options.max_seconds or job["duration"])
            target = min(job["total_frames"], math.ceil(target_seconds * job["fps"]))
            recorded = options.recorded_at.astimezone(timezone.utc).isoformat(timespec="milliseconds") if options.recorded_at else job["created_at"]
            self.db.update_job(job_id, status="queued", mode=options.mode, config=config.model_dump(), options=options.model_dump(mode="json"), target_frames=target, error=None, recorded_at=recorded, timestamp_basis="user-supplied" if options.recorded_at else "import-relative")
            self.db.event(job_id, "queued", f"Queued {'SCRIPTED DEMO (not AI)' if options.mode == 'demo' else 'real model inference'}; frame stride {config.frame_stride}.")
            self.publish(job_id)
            self.pool.submit(self._process, job_id, control, config, options)
            return self.db.job(job_id)

    def action(self, job_id, action):
        with self.lock:
            job = self.db.job(job_id)
            if job is None:
                raise KeyError(job_id)
            control = self.controls.get(job_id)
            if not control:
                raise JobConflict("This job is not active.")
            if action == "pause" and job["status"] == "running":
                control.gate.clear()
                self.db.update_job(job_id, status="paused")
            elif action == "resume" and job["status"] == "paused":
                self.db.update_job(job_id, status="running")
                control.gate.set()
            elif action == "cancel" and job["status"] in ("queued", "running", "paused"):
                control.cancel.set()
                control.gate.set()
                # Cancellation is cooperative. The terminal status is written after the current frame.
                self.db.event(job_id, "cancel_requested", "Cancellation requested. Finishing the current frame.")
                self.publish(job_id)
                return {"status": "cancelling"}
            else:
                raise JobConflict(f"Cannot {action} a {job['status']} job.")
            self.db.event(job_id, action, f"Processing {action} requested.")
            self.publish(job_id)
            return self.db.job(job_id)

    def _process(self, job_id, control, config, options):
        cap = None
        started = time.perf_counter()
        paused_seconds = 0.
        try:
            job = self.db.job(job_id)
            if control.cancel.is_set():
                self.db.update_job(job_id, status="cancelled", finished_at=utcnow())
                self.db.event(job_id, "cancelled", "Queued job cancelled before any frames were processed.")
                return
            with self.lock:
                self.db.update_job(job_id, status="running", started_at=utcnow())
            self.db.event(job_id, "started", "Processing started. Demo results are scripted." if options.mode == "demo" else "Real model inference started.")
            self.publish(job_id)
            cap = cv2.VideoCapture(str(inside(self.settings.data_dir, job["source_path"])))
            if not cap.isOpened():
                raise RuntimeError("The uploaded video is no longer readable.")
            detector = DemoDetector(self.settings.sample_dir) if options.mode == "demo" else self.model
            tracker = DemoTracker(config) if options.mode == "demo" else BoTSortTracker(config)
            engine = ViolationEngine(config)
            base_time = datetime.fromisoformat(job["recorded_at"])
            index, processed, detection_events, inference_ms_total = 0, 0, 0, 0.
            last_preview = 0.
            target = job["target_frames"]
            # Initialization and model warmup count towards active processing time.
            while index < target:
                if control.cancel.is_set():
                    break
                if not control.gate.is_set():
                    pause_start = time.perf_counter()
                    while not control.gate.wait(.1) and not control.cancel.is_set():
                        pass
                    paused_seconds += time.perf_counter() - pause_start
                    continue
                ok, frame = cap.read()
                if not ok:
                    # A tiny metadata discrepancy is tolerated; early decode failure is NOT success.
                    if index < target - max(2, int(job["fps"] * .1)):
                        raise RuntimeError(f"Video decode stopped early at frame {index} of {target}; the file may be corrupt.")
                    break
                timestamp = index / job["fps"]
                frame_index = index
                index += 1
                if frame_index % config.frame_stride:
                    continue
                if options.mode == "demo":
                    detections, infer_ms = detector.predict(frame, config, timestamp)
                else:
                    detections, infer_ms = detector.predict(frame, config)
                vehicles = tracker.update(detections, frame)
                visible = [d for d in detections if d.confidence >= config.confidence]
                tracks, records, crossings = engine.update(vehicles, visible, job["width"], job["height"], timestamp)
                occurred_at = (base_time + timedelta(seconds=timestamp)).isoformat(timespec="milliseconds")
                # Attach IDs to displayed vehicle detections without creating duplicate boxes.
                output = []
                for det in visible:
                    matches = [v for v in vehicles if v.class_name == det.class_name and iou(v.bbox, det.bbox) > .3]
                    if matches:
                        det.track_id = max(matches, key=lambda v: iou(v.bbox, det.bbox)).track_id
                    output.append(det.json())
                processed += 1
                detection_events += len(visible)
                inference_ms_total += infer_ms
                elapsed = max(.0001, time.perf_counter() - started - paused_seconds)
                frame_payload = {"frame_index": frame_index, "video_time": round(timestamp, 4), "occurred_at": occurred_at, "mode": options.mode, "detections": output, "tracks": tracks, "inference_ms": round(infer_ms, 3), "width": job["width"], "height": job["height"]}
                need_preview = records or time.perf_counter() - last_preview > .2 or index >= target
                annotated = annotate(frame, tracks, visible, config, options.mode, timestamp) if need_preview else None
                for record in records:
                    record["id"] = str(uuid.uuid4())
                    filename = f"{job_id}/{record['id']}_{record['violation_type']}.jpg"
                    record["evidence_filename"] = filename
                    # Evidence must exist before its database record is committed.
                    evidence = annotated.copy()
                    x1, y1, x2, y2 = map(int, record["vehicle_bbox"])
                    cv2.rectangle(evidence, (x1, y1), (x2, y2), (75, 84, 255), 4)
                    cv2.putText(evidence, f"EVIDENCE: #{record['track_id']} {record['violation_type']} | {record['votes']} votes", (12, evidence.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, .5, (115, 160, 255), 1, cv2.LINE_AA)
                    write_jpeg(inside(self.settings.data_dir / "evidence", filename), evidence)
                if need_preview:
                    if annotated.shape[1] > 1280:
                        annotated = cv2.resize(annotated, (1280, round(annotated.shape[0] * 1280 / annotated.shape[1])))
                    write_jpeg(self.settings.data_dir / "frames" / f"{job_id}.jpg", annotated)
                    last_preview = time.perf_counter()
                self.db.checkpoint(job_id, frame_payload, tracks, records, crossings, {"processed_frames": processed, "decoded_frames": index, "video_time": round(timestamp, 4), "elapsed": round(elapsed, 3), "processing_fps": round(processed / elapsed, 2), "inference_fps": round(1000 * processed / inference_ms_total, 2) if inference_ms_total else 0, "detection_events": detection_events, "progress": round(min(.999, index / target), 5)})
                self.publish(job_id)
                if options.mode == "demo":
                    control.cancel.wait(self.settings.demo_delay)
            status = "cancelled" if control.cancel.is_set() else "completed"
            final_elapsed = max(.0001, time.perf_counter() - started - paused_seconds)
            fields = {"status": status, "finished_at": utcnow(), "elapsed": round(final_elapsed, 3), "decoded_frames": index, "processing_fps": round(processed / final_elapsed, 2)}
            if status == "completed":
                fields["progress"] = 1.
            self.db.update_job(job_id, **fields)
            self.db.event(job_id, status, f"Processing {status}: {processed} sampled frames, {detection_events} detection events. Unique vehicles are counted separately.")
        except Exception as exc:
            log.exception("Processing job %s failed", job_id, extra={"job_id": job_id})
            message = str(exc)[:500] if isinstance(exc, (ValueError, RuntimeError)) else f"Processing failed ({type(exc).__name__}); see backend logs."
            self.db.update_job(job_id, status="failed", error=message, finished_at=utcnow())
            self.db.event(job_id, "failed", message, "error")
        finally:
            if cap is not None:
                cap.release()
            with self.lock:
                self.controls.pop(job_id, None)
            self.publish(job_id)

    def delete(self, job_id):
        with self.lock:
            job = self.db.job(job_id)
            if not job:
                raise KeyError(job_id)
            if job_id in self.controls or job["preview_status"] == "preparing":
                raise JobConflict("Cancel processing and wait for preview generation before deleting this job.")
            with self.db.connect() as c:
                c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            for relative in {job["source_path"], job["preview_path"]} - {None}:
                inside(self.settings.data_dir, relative).unlink(missing_ok=True)
            (self.settings.data_dir / "frames" / f"{job_id}.jpg").unlink(missing_ok=True)
            shutil.rmtree(self.settings.data_dir / "evidence" / job_id, ignore_errors=True)

    def close(self):
        with self.lock:
            self.closing = True
            for control in self.controls.values():
                control.cancel.set()
                control.gate.set()
        self.pool.shutdown(wait=True, cancel_futures=False)
        self.preview_pool.shutdown(wait=True, cancel_futures=False)
