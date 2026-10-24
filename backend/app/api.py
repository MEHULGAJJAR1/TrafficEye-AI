from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .analytics import Filters, analytics, get_filters, list_tracks, list_violations
from .config import RuntimeConfig
from .database import utcnow
from .demo import DEMO_NAME
from .inference import ModelUnavailable
from .processing import JobConflict
from .reporting import csv_report
from .schemas import LoginRequest, StartRequest
from .security import COOKIE, SESSION_SECONDS, inside, safe_filename
from .video import VideoInvalid, inspect_video


def public_job(job):
    if job is None:
        raise HTTPException(404, "Job not found.")
    result = {k: v for k, v in job.items() if k not in ("source_path", "preview_path")}
    result["video_url"] = f"/api/jobs/{job['id']}/video" if job["preview_status"] == "ready" else None
    result["frame_url"] = f"/api/jobs/{job['id']}/frame" if job["processed_frames"] else None
    return result


def router():
    r = APIRouter(prefix="/api")

    def authenticated(request: Request):
        request.app.state.auth.check(request)

    secure = APIRouter(dependencies=[Depends(authenticated)])

    @r.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "TrafficEye AI", "version": "1.0.0"}

    @r.get("/auth/status", tags=["authentication"])
    def auth_status(request: Request):
        auth = request.app.state.auth
        return {"authenticated": auth.valid_session(request.cookies.get(COOKIE)) or auth.valid_bearer(request.headers.get("authorization", "")), "key_location": "data/access.key", "session_hours": 12}

    @r.post("/auth/login", tags=["authentication"])
    def login(body: LoginRequest, request: Request, response: Response):
        value = request.app.state.auth.login(body.key, request.client.host if request.client else "local")
        response.set_cookie(COOKIE, value, max_age=SESSION_SECONDS, httponly=True, secure=request.app.state.settings.secure_cookie, samesite="strict", path="/")
        return {"authenticated": True}

    @secure.post("/auth/logout", tags=["authentication"])
    def logout(response: Response):
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
        return {"authenticated": False}

    @secure.get("/system", tags=["system"])
    def system(request: Request):
        state = request.app.state
        state.db.one("SELECT COUNT(*) AS n FROM jobs")  # verify the schema is actually readable
        size = 0
        for path in state.settings.data_dir.rglob("*"):
            try:
                if path.is_file():
                    size += path.stat().st_size
            except FileNotFoundError:
                pass  # a temporary file may be atomically replaced during this scan
        return {"api": "online", "database": "online", "model": state.model.status(state.configs.get()), "active_jobs": len(state.manager.controls), "worker_limit": 1, "storage_bytes": size, "max_upload_mb": state.settings.max_upload_mb, "sample_available": bool(state.manager.sample_hash), "demo_notice": "Demo objects and confidence values are scripted fixtures, never AI predictions.", "warnings": ["Helmet and seatbelt decisions can be unreliable for occluded, distant, poorly lit or unsuitable-angle views. Human review is mandatory.", "BoT-SORT IDs may fragment or switch. Unique tracks are not guaranteed to be unique real-world identities."]}

    @secure.get("/config", tags=["configuration"])
    def get_config(request: Request):
        return request.app.state.configs.get()

    @secure.put("/config", tags=["configuration"])
    def save_config(body: RuntimeConfig, request: Request):
        request.app.state.configs.save(body)
        request.app.state.db.event(None, "configuration", "Configuration saved. Changes apply to new/retried jobs only.")
        return body

    @secure.post("/model/validate", tags=["configuration"])
    def validate_model(request: Request):
        state = request.app.state
        try:
            state.model.load(state.configs.get())
        except ModelUnavailable as exc:
            status = state.model.status(state.configs.get())
            return {**status, "message": str(exc), "ready": False}
        return state.model.status(state.configs.get())

    @secure.get("/jobs", tags=["jobs"])
    def jobs(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        db = request.app.state.db
        return {"items": [public_job(v) for v in db.query("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))], "total": db.one("SELECT COUNT(*) AS n FROM jobs")["n"]}

    async def register(request, source, filename):
        state = request.app.state
        try:
            info = await run_in_threadpool(inspect_video, source, state.settings.max_video_seconds)
            is_demo = await run_in_threadpool(state.manager.is_demo, source)
        except VideoInvalid as exc:
            source.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        job_id = source.stem
        value = {"id": job_id, "filename": safe_filename(filename), "source_path": f"uploads/{source.name}", "created_at": utcnow(), "size_bytes": source.stat().st_size, "is_demo_source": int(is_demo), **info}
        state.db.create_job(value)
        state.db.event(job_id, "uploaded", f"Uploaded {value['filename']}. {'Verified synthetic fixture.' if is_demo else 'User-provided footage; requires a real custom model.'}")
        state.manager.prepare_preview(job_id)
        return public_job(state.db.job(job_id))

    @secure.post("/uploads", status_code=201, tags=["media"])
    async def upload(request: Request):
        state = request.app.state
        if state.db.one("SELECT COUNT(*) AS n FROM jobs")["n"] >= 200:
            raise HTTPException(409, "The workspace has 200 videos. Delete old jobs before adding more.")
        source = None
        try:
            async with request.form(max_files=1, max_fields=2, max_part_size=1024 * 1024) as form:
                file = form.get("file")
                from starlette.datastructures import UploadFile
                if not isinstance(file, UploadFile):
                    raise HTTPException(422, "Upload one video in the multipart 'file' field.")
                filename = safe_filename(file.filename or "")
                ext = Path(filename).suffix.lower()
                if ext not in (".mp4", ".avi", ".mov"):
                    raise HTTPException(415, "Supported video extensions: MP4, AVI and MOV.")
                source = state.settings.data_dir / "uploads" / f"{uuid.uuid4()}{ext}"
                limit, count = state.settings.max_upload_mb * 1024 * 1024, 0
                with source.open("wb") as output:
                    while chunk := await file.read(1024 * 1024):
                        count += len(chunk)
                        if count > limit:
                            raise HTTPException(413, f"The upload exceeds {state.settings.max_upload_mb} MB.")
                        await run_in_threadpool(output.write, chunk)
                if count == 0:
                    raise HTTPException(422, "The uploaded file is empty.")
            return await register(request, source, filename)
        except Exception:
            if source:
                # Only delete a file if registration did not commit a job that owns it.
                if not state.db.job(source.stem):
                    source.unlink(missing_ok=True)
            raise

    @secure.post("/samples/demo", status_code=201, tags=["media"])
    async def demo_sample(request: Request):
        state = request.app.state
        if not state.manager.sample_hash:
            raise HTTPException(409, "The sample is missing or its checksum is invalid. Run python scripts/prepare_sample.py.")
        if state.db.one("SELECT COUNT(*) AS n FROM jobs")["n"] >= 200:
            raise HTTPException(409, "Delete old jobs before importing more sample videos.")
        path = state.settings.data_dir / "uploads" / f"{uuid.uuid4()}.mp4"
        await run_in_threadpool(shutil.copyfile, state.settings.sample_dir / DEMO_NAME, path)
        return await register(request, path, DEMO_NAME)

    @secure.get("/jobs/{job_id}", tags=["jobs"])
    def job(job_id: UUID, request: Request):
        return public_job(request.app.state.db.job(str(job_id)))

    @secure.post("/jobs/{job_id}/start", tags=["jobs"])
    def start(job_id: UUID, body: StartRequest, request: Request):
        try:
            return public_job(request.app.state.manager.start(str(job_id), body))
        except KeyError as exc:
            raise HTTPException(404, "Job not found.") from exc
        except (JobConflict, ModelUnavailable) as exc:
            raise HTTPException(409, str(exc)) from exc

    @secure.post("/jobs/{job_id}/retry", tags=["jobs"])
    def retry(job_id: UUID, request: Request, body: StartRequest | None = None):
        try:
            job = request.app.state.db.job(str(job_id))
            if job is None:
                raise KeyError(str(job_id))
            options = body or StartRequest.model_validate(job["options"] or {})
            return public_job(request.app.state.manager.start(str(job_id), options, retry=True))
        except KeyError as exc:
            raise HTTPException(404, "Job not found.") from exc
        except (JobConflict, ModelUnavailable) as exc:
            raise HTTPException(409, str(exc)) from exc

    @secure.post("/jobs/{job_id}/{action}", tags=["jobs"])
    def control(job_id: UUID, action: Literal["pause", "resume", "cancel"], request: Request):
        try:
            result = request.app.state.manager.action(str(job_id), action)
            return public_job(result) if "id" in result else result
        except KeyError as exc:
            raise HTTPException(404, "Job not found.") from exc
        except JobConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @secure.delete("/jobs/{job_id}", tags=["jobs"])
    def delete(job_id: UUID, request: Request):
        try:
            request.app.state.manager.delete(str(job_id))
            return {"deleted": str(job_id)}
        except KeyError as exc:
            raise HTTPException(404, "Job not found.") from exc
        except JobConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @secure.get("/jobs/{job_id}/video", tags=["media"])
    def video(job_id: UUID, request: Request):
        state = request.app.state
        job = state.db.job(str(job_id))
        public_job(job)
        if job["preview_status"] != "ready" or not job["preview_path"]:
            raise HTTPException(409, "The browser preview is still being prepared or is unavailable.")
        path = inside(state.settings.data_dir, job["preview_path"])
        if not path.exists():
            raise HTTPException(404, "Preview file not found; re-upload the video.")
        return FileResponse(path, media_type="video/mp4")

    @secure.get("/jobs/{job_id}/frame", tags=["media"])
    def frame(job_id: UUID, request: Request):
        public_job(request.app.state.db.job(str(job_id)))
        path = request.app.state.settings.data_dir / "frames" / f"{job_id}.jpg"
        if not path.is_file():
            raise HTTPException(404, "No processed frame is available yet.")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @secure.get("/jobs/{job_id}/results", tags=["results"])
    def results(job_id: UUID, request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        public_job(request.app.state.db.job(str(job_id)))
        db = request.app.state.db
        return {"items": db.query("SELECT * FROM frames WHERE job_id=? ORDER BY frame_index DESC LIMIT ? OFFSET ?", (str(job_id), limit, offset)), "total": db.one("SELECT COUNT(*) AS n FROM frames WHERE job_id=?", (str(job_id),))["n"]}

    @secure.get("/tracks", tags=["results"])
    def tracks(request: Request, filters: Filters = Depends(get_filters), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return list_tracks(request.app.state.db, filters, limit, offset)

    @secure.get("/violations", tags=["results"])
    def violations(request: Request, filters: Filters = Depends(get_filters), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        return list_violations(request.app.state.db, filters, limit, offset)

    @secure.get("/analytics", tags=["analytics"])
    def stats(request: Request, filters: Filters = Depends(get_filters)):
        return analytics(request.app.state.db, filters)

    @secure.get("/events", tags=["results"])
    def events(request: Request, job_id: UUID | None = None, level: Literal["info", "warning", "error"] | None = None, limit: int = Query(50, ge=1, le=500), before: int | None = Query(None, ge=1)):
        clauses, params = ["1=1"], []
        for value, clause in ((str(job_id) if job_id else None, "job_id=?"), (level, "level=?"), (before, "id<?")):
            if value is not None:
                clauses.append(clause)
                params.append(value)
        return {"items": request.app.state.db.query(f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?", [*params, limit])}

    @secure.get("/evidence/{evidence_id}", tags=["media"])
    def evidence(evidence_id: UUID, request: Request, download: bool = False):
        row = request.app.state.db.one("SELECT evidence_filename FROM violations WHERE id=?", (str(evidence_id),))
        if not row:
            raise HTTPException(404, "Evidence record not found.")
        path = inside(request.app.state.settings.data_dir / "evidence", row["evidence_filename"])
        if not path.is_file():
            raise HTTPException(404, "The evidence image is missing. Check storage integrity.")
        return FileResponse(path, media_type="image/jpeg", filename=path.name if download else None)

    @secure.get("/reports.csv", tags=["reports"])
    def report(request: Request, filters: Filters = Depends(get_filters), kind: Literal["violations", "vehicles"] = "violations"):
        return StreamingResponse(csv_report(request.app.state.db, filters, kind), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="trafficeye_{kind}_{time.strftime("%Y%m%d")}.csv"', "Cache-Control": "no-store"})

    r.include_router(secure)

    @r.websocket("/ws/jobs/{job_id}")
    async def websocket(websocket: WebSocket, job_id: UUID):
        state, job_id = websocket.app.state, str(job_id)
        if not state.auth.ws_allowed(websocket):
            await websocket.close(code=1008)
            return
        if state.db.job(job_id) is None:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last = -1
        try:
            while True:
                if not state.auth.valid_session(websocket.cookies.get(COOKIE)):
                    await websocket.close(code=1008)
                    return
                version = state.hub.version(job_id)
                if version != last:
                    job = await run_in_threadpool(state.db.job, job_id)
                    if job is None:
                        await websocket.close(code=1000)
                        return
                    await websocket.send_json({"type": "job_update", "job": public_job(job), "version": version})
                    last = version
                try:
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=.5)
                    if message == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass

    return r
