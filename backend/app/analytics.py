"""All aggregates are derived from persisted observations; demo and real scopes stay explicit."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, Query


@dataclass
class Filters:
    job_id: str | None = None
    vehicle_class: str | None = None
    violation_type: str | None = None
    min_confidence: float = 0
    date_from: str | None = None
    date_to: str | None = None
    source: str = "all"


def get_filters(job_id: str | None = Query(None, max_length=36), vehicle_class: Literal["Bike", "Car", "Jeep", "Van"] | None = None, violation_type: Literal["No-Helmet", "No-Seatbelt"] | None = None, min_confidence: float = Query(0, ge=0, le=1), date_from: datetime | None = None, date_to: datetime | None = None, source: Literal["all", "real", "demo"] = "all"):
    for value in (date_from, date_to):
        if value is not None and value.tzinfo is None:
            raise HTTPException(422, "Date filters must include a timezone.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from cannot be after date_to.")
    iso = lambda v: v.astimezone(timezone.utc).isoformat(timespec="milliseconds") if v else None
    return Filters(job_id, vehicle_class, violation_type, min_confidence, iso(date_from), iso(date_to), source)


def track_scope(f: Filters):
    conditions, params = ["t.confidence>=?"], [f.min_confidence]
    for value, clause in ((f.job_id, "t.job_id=?"), (f.vehicle_class, "t.vehicle_class=?"), (f.date_from, "t.last_at>=?"), (f.date_to, "t.first_at<=?")):
        if value:
            conditions.append(clause)
            params.append(value)
    if f.source != "all":
        conditions.append("j.mode=?")
        params.append(f.source)
    return " AND ".join(conditions), params


def violation_scope(f: Filters):
    conditions, params = ["v.confidence>=?"], [f.min_confidence]
    for value, clause in ((f.violation_type, "v.violation_type=?"), (f.date_from, "v.occurred_at>=?"), (f.date_to, "v.occurred_at<=?")):
        if value:
            conditions.append(clause)
            params.append(value)
    return " AND ".join(conditions), params


def violation_query(f):
    ts, tp = track_scope(f)
    vs, vp = violation_scope(f)
    return f"FROM violations v JOIN jobs j ON j.id=v.job_id JOIN tracks t ON t.job_id=v.job_id AND t.track_id=v.track_id WHERE {ts} AND {vs}", tp + vp


def list_tracks(db, filters, limit=100, offset=0):
    scope, params = track_scope(filters)
    if filters.violation_type:
        scope += " AND EXISTS(SELECT 1 FROM violations vv WHERE vv.job_id=t.job_id AND vv.track_id=t.track_id AND vv.violation_type=?)"
        params.append(filters.violation_type)
    base = f"FROM tracks t JOIN jobs j ON j.id=t.job_id WHERE {scope}"
    count = db.one(f"SELECT COUNT(*) AS total {base}", params)["total"]
    rows = db.query(f"SELECT t.*,j.mode,j.filename,(SELECT COUNT(*) FROM violations v WHERE v.job_id=t.job_id AND v.track_id=t.track_id) AS violation_count {base} ORDER BY t.last_at DESC,t.track_id LIMIT ? OFFSET ?", [*params, limit, offset])
    return {"items": rows, "total": count, "limit": limit, "offset": offset}


def list_violations(db, filters, limit=100, offset=0):
    base, params = violation_query(filters)
    total = db.one(f"SELECT COUNT(*) AS total {base}", params)["total"]
    rows = db.query(f"SELECT v.*,j.mode,j.filename,j.timestamp_basis {base} ORDER BY v.occurred_at DESC LIMIT ? OFFSET ?", [*params, limit, offset])
    for row in rows:
        row["evidence_url"] = f"/api/evidence/{row['id']}"
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def analytics(db, filters):
    ts, tp = track_scope(filters)
    tracks = db.query(f"SELECT t.*,j.mode FROM tracks t JOIN jobs j ON j.id=t.job_id WHERE {ts}", tp)
    vb, vp = violation_query(filters)
    violations = db.query(f"SELECT v.*,j.mode {vb}", vp)
    total = len(tracks)
    violating_ids = {(v["job_id"], v["track_id"]) for v in violations}
    class_counts = defaultdict(int)
    for track in tracks:
        class_counts[track["vehicle_class"]] += 1
    # Count all qualifying box observations, including safety classes; never call these vehicles.
    conditions, params = ["json_extract(d.value,'$.confidence')>=?"], [filters.min_confidence]
    for value, clause in ((filters.job_id, "f.job_id=?"), (filters.vehicle_class, "json_extract(d.value,'$.class_name')=?"), (filters.date_from, "f.occurred_at>=?"), (filters.date_to, "f.occurred_at<=?")):
        if value:
            conditions.append(clause)
            params.append(value)
    if filters.source != "all":
        conditions.append("j.mode=?")
        params.append(filters.source)
    boxes = db.query(f"SELECT json_extract(d.value,'$.class_name') AS name,COUNT(*) AS value FROM frames f JOIN jobs j ON j.id=f.job_id,json_each(f.payload,'$.detections') d WHERE {' AND '.join(conditions)} GROUP BY name", params)
    cross_conditions, cross_params = [ts], list(tp)
    if filters.date_from:
        cross_conditions.append("c.occurred_at>=?")
        cross_params.append(filters.date_from)
    if filters.date_to:
        cross_conditions.append("c.occurred_at<=?")
        cross_params.append(filters.date_to)
    crossings = db.query(f"SELECT c.direction,COUNT(*) AS n FROM crossings c JOIN tracks t ON t.job_id=c.job_id AND t.track_id=c.track_id JOIN jobs j ON j.id=c.job_id WHERE {' AND '.join(cross_conditions)} GROUP BY c.direction", cross_params)
    directions = {r["direction"]: r["n"] for r in crossings}
    timeline = defaultdict(lambda: {"vehicles": 0, "helmet": 0, "seatbelt": 0, "violations": 0})
    def bucket(item, key, time_key):
        if filters.job_id:
            seconds = int(float(item[time_key]) // 10) * 10
            return f"{seconds // 60:02d}:{seconds % 60:02d}"
        return item[key][:16].replace("T", " ")
    for track in tracks:
        timeline[bucket(track, "first_at", "first_time")]["vehicles"] += 1
    for violation in violations:
        slot = timeline[bucket(violation, "occurred_at", "video_time")]
        slot["helmet" if violation["violation_type"] == "No-Helmet" else "seatbelt"] += 1
        slot["violations"] += 1
    job_conditions, job_params = ["mode IS NOT NULL"], []
    if filters.job_id:
        job_conditions.append("id=?")
        job_params.append(filters.job_id)
    if filters.source != "all":
        job_conditions.append("mode=?")
        job_params.append(filters.source)
    jobs = db.query(f"SELECT mode,status,processing_fps,inference_fps,elapsed,processed_frames FROM jobs WHERE {' AND '.join(job_conditions)} ORDER BY created_at DESC", job_params)
    modes = sorted({j["mode"] for j in jobs})
    active = next((j for j in jobs if j["status"] in ("running", "paused")), jobs[0] if jobs else {})
    return {"summary": {"total_vehicles": total, "unique_tracked_vehicles": total, "motorcycles": class_counts["Bike"], "cars": class_counts["Car"], "four_wheelers": sum(class_counts[k] for k in ("Car", "Jeep", "Van")), "helmet_violations": sum(v["violation_type"] == "No-Helmet" for v in violations), "seatbelt_violations": sum(v["violation_type"] == "No-Seatbelt" for v in violations), "confirmed_violations": len(violations), "unique_violating_vehicles": len(violating_ids), "violation_rate": round(100 * len(violating_ids) / total, 2) if total else 0, "detection_events": sum(r["value"] for r in boxes), "vehicles_in": directions.get("IN", 0), "vehicles_out": directions.get("OUT", 0), "processing_fps": active.get("processing_fps", 0), "inference_fps": active.get("inference_fps", 0), "processed_frames": sum(j["processed_frames"] for j in jobs)}, "class_distribution": [{"name": k, "value": class_counts[k]} for k in ("Bike", "Car", "Jeep", "Van")], "detection_distribution": boxes, "timeline": [{"label": key, **values} for key, values in sorted(timeline.items())], "source_modes": modes, "denominators": {"violation_rate": "100 × unique (job, track) vehicles with a matching confirmed violation ÷ all unique (job, track) vehicles in the selected date/class/confidence/source scope. Violation-type filters affect only the numerator.", "class_share": "Unique vehicles of this class ÷ all unique vehicles in scope.", "detection_events": "One class-labelled box observation in one processed frame; the same vehicle can create many observations. Safety boxes are included unless class-filtered.", "dates": "Track presence overlaps the selected UTC interval. Event dates use supplied recording time + video offset, otherwise import time + offset; original capture time is unknown.", "counting": "One finite-line crossing per (job, track, direction); the same vehicle may count once IN and once OUT.", "fps": "Processing FPS is sampled frames / active elapsed seconds for the current or latest scoped job. Inference FPS excludes decode/tracking/database; it is zero in demo mode. FPS is not date/class filtered."}}
