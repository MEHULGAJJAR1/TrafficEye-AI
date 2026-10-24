"""Streaming, spreadsheet-safe CSV. No untested PDF feature is advertised."""
import csv
import io

from .analytics import track_scope, violation_query

COLUMNS = ["job_id", "source_mode", "vehicle_id", "timestamp_utc", "video_time_seconds", "vehicle_class", "helmet_status", "seatbelt_status", "violation_type", "confidence", "zone", "evidence_filename", "timestamp_basis"]


def csv_safe(value):
    text = str(value) if value is not None else ""
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def csv_report(db, filters, kind="violations"):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    yield "\ufeff" + output.getvalue()  # UTF-8 BOM makes Excel import reliably.
    output.seek(0)
    output.truncate(0)
    if kind == "violations":
        base, params = violation_query(filters)
        sql = f"SELECT v.*,j.mode,j.timestamp_basis {base} ORDER BY v.occurred_at,v.track_id"
    else:
        scope, params = track_scope(filters)
        if filters.violation_type:
            scope += " AND v.violation_type=?"
            params.append(filters.violation_type)
        sql = f"""SELECT t.job_id,t.track_id,t.first_at AS occurred_at,t.first_time AS video_time,t.vehicle_class,
        t.helmet_status,t.seatbelt_status,t.confidence,t.zone,COALESCE(v.violation_type,'') AS violation_type,
        COALESCE(v.evidence_filename,'') AS evidence_filename,j.mode,j.timestamp_basis FROM tracks t JOIN jobs j ON j.id=t.job_id
        LEFT JOIN violations v ON v.job_id=t.job_id AND v.track_id=t.track_id WHERE {scope} ORDER BY t.first_at,t.track_id"""
    with db.connect() as connection:
        for row in connection.execute(sql, params):
            values = [row["job_id"], row["mode"], row["track_id"], row["occurred_at"], f"{row['video_time']:.3f}", row["vehicle_class"], row["helmet_status"], row["seatbelt_status"], row["violation_type"], f"{row['confidence']:.4f}", row["zone"], row["evidence_filename"], row["timestamp_basis"]]
            writer.writerow([csv_safe(v) for v in values])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
