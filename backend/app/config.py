"""Validated environment and per-job configuration. Paths never depend on the shell cwd."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CLASSES = ("Bike", "Car", "Jeep", "Van", "Helmet", "No-Helmet", "Seatbelt", "No-Seatbelt")
VEHICLE_CLASSES = ("Bike", "Car", "Jeep", "Van")


class Zone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9 _-]+$")
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=20)

    @field_validator("polygon")
    @classmethod
    def valid_points(cls, value):
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in value):
            raise ValueError("Zone coordinates must be normalized to [0, 1].")
        area = abs(sum(value[i][0] * value[(i + 1) % len(value)][1] - value[(i + 1) % len(value)][0] * value[i][1] for i in range(len(value))))
        if area < 0.001:
            raise ValueError("Zone polygon must have a nonzero area.")
        # Reject self-intersecting polygons; convexity is NOT required.
        def turn(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        n = len(value)
        for i in range(n):
            for j in range(i + 1, n):
                if j == i + 1 or (i == 0 and j == n - 1):
                    continue
                a, b, c, d = value[i], value[(i + 1) % n], value[j], value[(j + 1) % n]
                if turn(a, b, c) * turn(a, b, d) <= 0 and turn(c, d, a) * turn(c, d, b) <= 0:
                    raise ValueError("Zone polygon must not self-intersect.")
        return value


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model_file: str = Field(default="traffic-custom.pt", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.pt$")
    device: str = Field(default="auto", pattern=r"^(auto|cpu|cuda(?::[0-9]+)?|[0-9]+|mps)$")
    imgsz: int = Field(default=640, ge=320, le=1536, multiple_of=32)
    confidence: float = Field(default=0.40, ge=0.05, le=0.95)
    violation_confidence: float = Field(default=0.65, ge=0.1, le=0.99)
    iou: float = Field(default=0.5, ge=0.1, le=0.95)
    frame_stride: int = Field(default=1, ge=1, le=10)
    vote_window: int = Field(default=7, ge=3, le=60)
    min_votes: int = Field(default=4, ge=2, le=60)
    vote_ratio: float = Field(default=0.67, ge=0.5, le=1)
    min_evidence_seconds: float = Field(default=0.25, ge=0.1, le=10)
    association_overlap: float = Field(default=0.55, ge=0.1, le=1)
    ambiguity_margin: float = Field(default=0.15, ge=0.01, le=0.5)
    bike_top_margin: float = Field(default=0.65, ge=0, le=1.5)
    min_vehicle_pixels: int = Field(default=20, ge=8, le=256)
    duplicate_iou: float = Field(default=0.75, ge=0.5, le=0.99)
    duplicate_seconds: float = Field(default=2.5, ge=0, le=30)
    track_high_thresh: float = Field(default=0.4, ge=0.05, le=0.95)
    track_low_thresh: float = Field(default=0.1, ge=0.01, le=0.9)
    new_track_thresh: float = Field(default=0.5, ge=0.05, le=0.99)
    track_buffer: int = Field(default=30, ge=1, le=300)
    match_thresh: float = Field(default=0.8, ge=0.1, le=0.99)
    gmc_method: Literal["sparseOptFlow", "none"] = "sparseOptFlow"
    zones: list[Zone] = Field(default_factory=lambda: [Zone(name="Main carriageway", polygon=[(0, 0), (1, 0), (1, 1), (0, 1)])], min_length=1, max_length=8)
    count_line: list[tuple[float, float]] = Field(default_factory=lambda: [(0, 0.55), (1, 0.55)], min_length=2, max_length=2)
    positive_direction: Literal["IN", "OUT"] = "IN"
    line_hysteresis: float = Field(default=0.01, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def consistent(self):
        if self.min_votes > self.vote_window:
            raise ValueError("min_votes cannot exceed vote_window.")
        if self.violation_confidence < self.confidence:
            raise ValueError("violation_confidence must be at least confidence.")
        if self.track_low_thresh >= self.track_high_thresh:
            raise ValueError("track_low_thresh must be less than track_high_thresh.")
        if len({z.name for z in self.zones}) != len(self.zones):
            raise ValueError("Zone names must be unique.")
        a, b = self.count_line
        if any(not 0 <= v <= 1 for p in self.count_line for v in p) or sum((a[i] - b[i]) ** 2 for i in (0, 1)) < .0025:
            raise ValueError("Count line must contain two distinct normalized points.")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TE_", env_file=str(ROOT / ".env"), extra="ignore")
    data_dir: Path = ROOT / "data"
    model_dir: Path = ROOT / "models"
    sample_dir: Path = ROOT / "samples"
    max_upload_mb: int = Field(default=500, ge=1, le=4096)
    max_video_seconds: int = Field(default=7200, ge=60, le=86400)
    max_queued_jobs: int = Field(default=4, ge=1, le=20)
    api_key: str = ""
    secure_cookie: bool = False
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173", "http://localhost:8000"]
    demo_delay: float = Field(default=0.025, ge=0, le=0.2)
    torch_threads: int = Field(default=2, ge=1, le=32)

    def prepare(self):
        self.data_dir = (self.data_dir if self.data_dir.is_absolute() else ROOT / self.data_dir).resolve()
        self.model_dir = (self.model_dir if self.model_dir.is_absolute() else ROOT / self.model_dir).resolve()
        self.sample_dir = (self.sample_dir if self.sample_dir.is_absolute() else ROOT / self.sample_dir).resolve()
        for sub in ("", "uploads", "previews", "evidence", "frames"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)


class ConfigStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "settings.json"
        self.lock = threading.RLock()
        self.value = RuntimeConfig.model_validate_json(self.path.read_text()) if self.path.exists() else RuntimeConfig()

    def get(self) -> RuntimeConfig:
        with self.lock:
            return self.value.model_copy(deep=True)

    def save(self, value: RuntimeConfig):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value.model_dump(), indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            self.value = value.model_copy(deep=True)
