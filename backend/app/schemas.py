from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=512)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["real", "demo"] = "real"
    max_seconds: float | None = Field(default=60, ge=1, le=86400)
    recorded_at: datetime | None = None

    @field_validator("recorded_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("recorded_at must include a timezone (e.g. 2026-10-23T10:00:00+05:30).")
        return value
