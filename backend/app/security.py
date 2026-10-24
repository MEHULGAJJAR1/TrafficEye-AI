"""Single-operator local authentication; opaque files are never publicly mounted."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, WebSocket

COOKIE = "te_session"
SESSION_SECONDS = 12 * 3600


def safe_filename(name: str) -> str:
    import re
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]
    return name or "video.mp4"


def inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise HTTPException(400, "Invalid file path.")
    return candidate


class Auth:
    def __init__(self, settings):
        self.settings = settings
        key_path = settings.data_dir / "access.key"
        if settings.api_key:
            if len(settings.api_key) < 24:
                raise ValueError("TE_API_KEY must contain at least 24 characters.")
            self.key = settings.api_key
        else:
            if not key_path.exists():
                # Exclusive creation avoids races if two processes are started accidentally.
                try:
                    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w") as file:
                        file.write(secrets.token_urlsafe(32))
                except FileExistsError:
                    pass
            self.key = key_path.read_text().strip()
            if len(self.key) < 24:
                raise ValueError("The local access.key is invalid. Stop the backend, remove that file and run scripts/init_workspace.py to generate a new private key.")
        self.secret = hashlib.sha256((self.key + "TrafficEye session v1").encode()).digest()
        self.attempts: dict[str, list[float]] = {}
        import threading
        self.lock = threading.Lock()
        logging.getLogger("trafficeye").info("Access key is stored locally at %s (never committed or packaged).", key_path)

    def session(self):
        payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(12)}"
        return f"{payload}.{hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()}"

    def valid_session(self, value: str | None):
        if not value:
            return False
        try:
            expiry, nonce, signature = value.split(".")
            if int(expiry) < time.time() or int(expiry) > time.time() + SESSION_SECONDS + 60:
                return False
            expected = hmac.new(self.secret, f"{expiry}.{nonce}".encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        except (ValueError, TypeError):
            return False

    def valid_bearer(self, value: str):
        return value.startswith("Bearer ") and hmac.compare_digest(value[7:], self.key)

    def check(self, request: Request):
        if not (self.valid_bearer(request.headers.get("authorization", "")) or self.valid_session(request.cookies.get(COOKIE))):
            raise HTTPException(401, "Unlock TrafficEye with the access key from data/access.key.")

    def valid_origin(self, origin: str | None, host: str | None):
        if not origin:
            return True  # CLI requests have no browser origin; credentials are still required.
        try:
            url = urlsplit(origin)
            return url.scheme in ("http", "https") and (origin in self.settings.allowed_origins or url.netloc == host)
        except ValueError:
            return False

    def ws_allowed(self, websocket: WebSocket):
        return self.valid_session(websocket.cookies.get(COOKIE)) and self.valid_origin(websocket.headers.get("origin"), websocket.headers.get("host"))

    def login(self, key: str, ip: str):
        now = time.monotonic()
        with self.lock:
            if len(self.attempts) > 2048:
                self.attempts = {k: v for k, v in self.attempts.items() if v and now - v[-1] < 300}
            attempts = [v for v in self.attempts.get(ip, []) if now - v < 300]
            if len(attempts) >= 10:
                raise HTTPException(429, "Too many unlock attempts. Wait five minutes.")
            if not hmac.compare_digest(key, self.key):
                self.attempts[ip] = attempts + [now]
                raise HTTPException(401, "The access key is incorrect.")
            self.attempts.pop(ip, None)
        return self.session()
