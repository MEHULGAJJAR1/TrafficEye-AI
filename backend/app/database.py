"""SQLite repositories: short-lived connections, WAL, bound parameters, atomic checkpoints."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, source_path TEXT NOT NULL,
 preview_path TEXT, preview_status TEXT NOT NULL DEFAULT 'preparing',
 created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
 status TEXT NOT NULL DEFAULT 'uploaded', mode TEXT, is_demo_source INTEGER NOT NULL DEFAULT 0,
 width INTEGER NOT NULL, height INTEGER NOT NULL, fps REAL NOT NULL, total_frames INTEGER NOT NULL,
 duration REAL NOT NULL, size_bytes INTEGER NOT NULL, codec TEXT,
 processed_frames INTEGER NOT NULL DEFAULT 0, decoded_frames INTEGER NOT NULL DEFAULT 0,
 target_frames INTEGER NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0,
 video_time REAL NOT NULL DEFAULT 0, elapsed REAL NOT NULL DEFAULT 0,
 processing_fps REAL NOT NULL DEFAULT 0, inference_fps REAL NOT NULL DEFAULT 0,
 detection_events INTEGER NOT NULL DEFAULT 0, last_result TEXT NOT NULL DEFAULT '{}',
 error TEXT, config TEXT, options TEXT, timestamp_basis TEXT NOT NULL DEFAULT 'import-relative',
 recorded_at TEXT
);
CREATE TABLE IF NOT EXISTS tracks(
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 track_id INTEGER NOT NULL, vehicle_class TEXT NOT NULL,
 first_time REAL NOT NULL, last_time REAL NOT NULL, first_at TEXT NOT NULL, last_at TEXT NOT NULL,
 confidence REAL NOT NULL, observations INTEGER NOT NULL DEFAULT 1,
 helmet_status TEXT NOT NULL DEFAULT 'unknown', seatbelt_status TEXT NOT NULL DEFAULT 'unknown',
 zone TEXT NOT NULL, bbox TEXT NOT NULL,
 PRIMARY KEY(job_id,track_id)
);
CREATE TABLE IF NOT EXISTS frames(
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, frame_index INTEGER NOT NULL,
 video_time REAL NOT NULL, occurred_at TEXT NOT NULL, detection_count INTEGER NOT NULL,
 inference_ms REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(job_id,frame_index)
);
CREATE TABLE IF NOT EXISTS violations(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 track_id INTEGER NOT NULL, occurred_at TEXT NOT NULL, video_time REAL NOT NULL,
 vehicle_class TEXT NOT NULL, violation_type TEXT NOT NULL,
 helmet_status TEXT NOT NULL, seatbelt_status TEXT NOT NULL,
 confidence REAL NOT NULL, zone TEXT NOT NULL, evidence_filename TEXT NOT NULL,
 vehicle_bbox TEXT NOT NULL, object_bbox TEXT NOT NULL, votes INTEGER NOT NULL,
 UNIQUE(job_id,track_id,violation_type)
);
CREATE TABLE IF NOT EXISTS crossings(
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, track_id INTEGER NOT NULL,
 direction TEXT NOT NULL, video_time REAL NOT NULL, occurred_at TEXT NOT NULL,
 PRIMARY KEY(job_id,track_id,direction)
);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL,
 payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_violation_time ON violations(occurred_at);
CREATE INDEX IF NOT EXISTS idx_frames_job ON frames(job_id,video_time);
CREATE INDEX IF NOT EXISTS idx_tracks_class ON tracks(vehicle_class);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id,id DESC);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def row_dict(row):
    if row is None:
        return None
    value = dict(row)
    for key in ("last_result", "config", "options", "payload", "bbox", "vehicle_bbox", "object_bbox"):
        if key in value and value[key] is not None:
            value[key] = json.loads(value[key])
    if "is_demo_source" in value:
        value["is_demo_source"] = bool(value["is_demo_source"])
    return value


class Database:
    JOB_COLUMNS = {"preview_path", "preview_status", "started_at", "finished_at", "status", "mode", "processed_frames", "decoded_frames", "target_frames", "progress", "video_time", "elapsed", "processing_fps", "inference_fps", "detection_events", "last_result", "error", "config", "options", "timestamp_basis", "recorded_at"}

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
            if version != 1:
                raise RuntimeError(f"Unsupported database schema {version}; back up the database before upgrading.")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, sql: str, params=()):
        with self.connect() as c:
            return [row_dict(r) for r in c.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()):
        with self.connect() as c:
            return row_dict(c.execute(sql, params).fetchone())

    def job(self, job_id: str):
        return self.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def create_job(self, value: dict):
        keys = tuple(value)
        allowed = {r[1] for r in self._columns("jobs")}
        if not set(keys) <= allowed:
            raise ValueError("Invalid job field.")
        with self.connect() as c:
            c.execute(f"INSERT INTO jobs({','.join(keys)}) VALUES({','.join('?' for _ in keys)})", tuple(value[k] for k in keys))

    def _columns(self, table):
        with self.connect() as c:
            return c.execute(f"PRAGMA table_info({table})").fetchall()

    def update_job(self, job_id, **fields):
        if not fields or not fields.keys() <= self.JOB_COLUMNS:
            raise ValueError("Invalid job update.")
        values = [dumps(v) if k in ("last_result", "config", "options") and v is not None else v for k, v in fields.items()]
        with self.connect() as c:
            c.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in fields)} WHERE id=?", (*values, job_id))

    def event(self, job_id, kind, message, level="info", payload=None):
        with self.connect() as c:
            details = dict(payload or {})
            if job_id:
                job = c.execute("SELECT mode FROM jobs WHERE id=?", (job_id,)).fetchone()
                if job and job["mode"]:
                    details.setdefault("mode", job["mode"])
            c.execute("INSERT INTO events(job_id,created_at,level,kind,message,payload) VALUES(?,?,?,?,?,?)", (job_id, utcnow(), level, kind, message, dumps(details)))

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET status='interrupted',error='Processing was interrupted by an application restart. Retry to reprocess from frame zero.',finished_at=? WHERE status IN ('queued','running','paused')", (utcnow(),))
            c.execute("UPDATE jobs SET preview_status='pending' WHERE preview_status='preparing'")

    def clear_results(self, job_id):
        with self.connect() as c:
            for table in ("tracks", "frames", "violations", "crossings"):
                c.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
        self.update_job(job_id, processed_frames=0, decoded_frames=0, detection_events=0, progress=0, video_time=0, elapsed=0, processing_fps=0, inference_fps=0, last_result={}, error=None, finished_at=None)

    def checkpoint(self, job_id, frame, tracks, violations, crossings, progress):
        with self.connect() as c:
            c.execute("INSERT INTO frames(job_id,frame_index,video_time,occurred_at,detection_count,inference_ms,payload) VALUES(?,?,?,?,?,?,?)", (job_id, frame["frame_index"], frame["video_time"], frame["occurred_at"], len(frame["detections"]), frame["inference_ms"], dumps(frame)))
            for t in tracks:
                c.execute("""INSERT INTO tracks(job_id,track_id,vehicle_class,first_time,last_time,first_at,last_at,confidence,helmet_status,seatbelt_status,zone,bbox)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id,track_id) DO UPDATE SET
                 last_time=excluded.last_time,last_at=excluded.last_at,confidence=MAX(tracks.confidence,excluded.confidence),
                 observations=tracks.observations+1,helmet_status=excluded.helmet_status,seatbelt_status=excluded.seatbelt_status,
                 zone=excluded.zone,bbox=excluded.bbox""", (job_id, t["track_id"], t["class_name"], frame["video_time"], frame["video_time"], frame["occurred_at"], frame["occurred_at"], t["confidence"], t["helmet_status"], t["seatbelt_status"], t["zone"], dumps(t["bbox"])))
            for v in violations:
                c.execute("""INSERT OR IGNORE INTO violations(id,job_id,track_id,occurred_at,video_time,vehicle_class,violation_type,helmet_status,seatbelt_status,confidence,zone,evidence_filename,vehicle_bbox,object_bbox,votes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (v["id"], job_id, v["track_id"], frame["occurred_at"], frame["video_time"], v["vehicle_class"], v["violation_type"], v["helmet_status"], v["seatbelt_status"], v["confidence"], v["zone"], v["evidence_filename"], dumps(v["vehicle_bbox"]), dumps(v["object_bbox"]), v["votes"]))
                c.execute("INSERT INTO events(job_id,created_at,level,kind,message,payload) VALUES(?,?,?,?,?,?)", (job_id, utcnow(), "warning", "violation", f"{v['violation_type']} confirmed for {v['vehicle_class']} #{v['track_id']}", dumps({"violation_id": v["id"], "video_time": frame["video_time"], "mode": frame["mode"]})))
            for cr in crossings:
                cur = c.execute("INSERT OR IGNORE INTO crossings(job_id,track_id,direction,video_time,occurred_at) VALUES(?,?,?,?,?)", (job_id, cr["track_id"], cr["direction"], frame["video_time"], frame["occurred_at"]))
                if cur.rowcount:
                    c.execute("INSERT INTO events(job_id,created_at,level,kind,message,payload) VALUES(?,?,?,?,?,?)", (job_id, utcnow(), "info", "crossing", f"Vehicle #{cr['track_id']} crossed {cr['direction']}", dumps({**cr, "mode": frame["mode"]})))
            progress = {**progress, "last_result": dumps(frame)}
            c.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in progress)} WHERE id=?", (*progress.values(), job_id))
