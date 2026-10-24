"""TrafficEye ASGI entrypoint: python -m uvicorn backend.app.main:app --port 8000."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router
from .config import ConfigStore, Settings
from .database import Database
from .events import EventHub
from .inference import ModelService
from .processing import JobManager
from .security import Auth
from .logging_config import configure_logging

configure_logging()


class RequestLimit:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Malformed Content-Length."}, status_code=400)(scope, receive, send)
        if size < 0 or size > self.max_bytes:
            return await JSONResponse({"detail": "Request body exceeds the configured upload limit."}, status_code=413)(scope, receive, send)
        received = 0
        class TooLarge(Exception):
            pass
        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise TooLarge()
            return message
        try:
            await self.app(scope, limited_receive, send)
        except TooLarge:
            await JSONResponse({"detail": "Request body exceeds the configured upload limit."}, status_code=413)(scope, receive, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    settings.prepare()

    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings
        app.state.db = Database(settings.data_dir / "trafficeye.sqlite3")
        app.state.configs = ConfigStore(settings.data_dir)
        app.state.auth = Auth(settings)
        app.state.hub = EventHub()
        app.state.model = ModelService(settings)
        app.state.manager = JobManager(settings, app.state.db, app.state.configs, app.state.model, app.state.hub)
        yield
        # Shutdown waits for cooperative cancellation so SQLite is never abandoned mid-write.
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(app.state.manager.close)

    app = FastAPI(title="TrafficEye AI", version="1.0.0", description="Authenticated, local-first traffic video analysis. All demo observations are explicitly scripted. Use a Bearer access key or the login session for private routes.", docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json", lifespan=lifespan)
    app.add_middleware(RequestLimit, max_bytes=settings.max_upload_mb * 1024 * 1024 + 1024 * 1024)
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Prevent browser CSRF even for an authenticated HttpOnly cookie.
        if request.method not in ("GET", "HEAD", "OPTIONS") and hasattr(request.app.state, "auth"):
            if not request.app.state.auth.valid_origin(request.headers.get("origin"), request.headers.get("host")):
                return JSONResponse({"detail": "Untrusted request origin."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo secret inputs or non-finite JSON values from validation errors.
        details = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger("trafficeye").exception("Unhandled API failure: %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse({"detail": "An unexpected backend error occurred. See the backend log; your saved results are retained."}, status_code=500)

    app.include_router(router())
    return app


app = create_app()
