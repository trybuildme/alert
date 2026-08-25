"""Application settings via pydantic-settings.

Environment variables keep their historical names (NOAH_*, EARTHQUAKE_*)
via explicit aliases, so existing deployments and docker-compose files
continue to work unchanged. Every field is overridable by env; defaults
match the previous hand-rolled os.getenv configuration.
"""

from __future__ import annotations

import os

from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _default_eq_db() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "data",
                        "earthquakes.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", frozen=False,
        validate_assignment=False, case_sensitive=True)

    APP_NAME: str = "NOAH"
    VERSION: str = "1.0.0"

    # Redis (optional at dev time; falls back to filesystem + memory)
    REDIS_URL: str = Field(
        "redis://localhost:6380/0",
        validation_alias=AliasChoices("REDIS_URL"))

    # Filesystem tile cache
    TILE_CACHE_DIR: str = Field(
        "/tmp/noah-tilecache",
        validation_alias=AliasChoices("NOAH_TILE_CACHE_DIR"))
    FS_CACHE_MAX_AGE_S: int = Field(
        24 * 3600, validation_alias=AliasChoices("NOAH_FS_CACHE_MAX_AGE"))

    # Tile rendering
    TILE_SIZE: int = 256

    # CORS — restrictive by default; extend via comma-separated env var
    # (e.g. NOAH_CORS_ORIGINS="http://localhost:3010,https://noah.example.ph")
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3010",
                                 "http://127.0.0.1:3010"],
        validation_alias=AliasChoices("NOAH_CORS_ORIGINS"))

    # Per-IP rate limiting (see app/core/ratelimit.py for buckets)
    RATE_LIMIT_ENABLED: bool = Field(
        True, validation_alias=AliasChoices("NOAH_RATE_LIMIT_ENABLED"))

    # --- Public exposure hardening ---
    # Optional shared bearer token; empty string disables auth entirely.
    # Clients send "Authorization: Bearer <token>" or ?access_token= (SSE).
    AUTH_TOKEN: str = Field(
        "", validation_alias=AliasChoices("NOAH_AUTH_TOKEN"))
    # Proxy IPs/CIDRs whose X-Forwarded-For header may be trusted when
    # resolving the real client IP for rate limiting. Empty = direct only.
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("NOAH_TRUSTED_PROXIES"))

    # --- Earthquake intelligence module (docs/earthquake/) ---
    EARTHQUAKE_ENABLED: bool = True
    EARTHQUAKE_POLL_INTERVAL: int = 300
    EARTHQUAKE_MIN_MAGNITUDE: float = 2.5
    # Ingestion lookback window in minutes (overlaps slightly to be safe)
    EARTHQUAKE_LOOKBACK_MINUTES: int = 180
    # One-time history backfill at startup (days); 0 disables
    EARTHQUAKE_BACKFILL_DAYS: int = 30
    # Map/API default query window in days
    EARTHQUAKE_HISTORY_DAYS: int = 30
    EARTHQUAKE_MAX_DEPTH_KM: float = 800
    EARTHQUAKE_DB_PATH: str = Field(
        default_factory=_default_eq_db,
        validation_alias=AliasChoices("NOAH_EQ_DB"))
    # USGS bounding box, order: minlon,minlat,maxlon,maxlat
    # (default: Philippines region). Empty string = global feed.
    EARTHQUAKE_BBOX: str = "115,4,127,21"
    EARTHQUAKE_ALERT_ENABLED: bool = True
    EARTHQUAKE_ALERT_RULES_PATH: str = Field(
        "", validation_alias=AliasChoices("NOAH_EQ_ALERT_RULES"))
    EARTHQUAKE_WS_ENABLED: bool = True
    # Regional monitoring focus (default: Aurora Province, PH)
    NOAH_EQ_REF_LAT: float = 15.78
    NOAH_EQ_REF_LON: float = 121.55
    NOAH_EQ_REF_RADIUS_KM: float = 150

    # --- Notifications (dispatcher channels) ---
    ALERT_RETENTION_DAYS: int = Field(
        90, validation_alias=AliasChoices("NOAH_ALERT_RETENTION_DAYS"))
    SMTP_HOST: str = Field("", validation_alias=AliasChoices("NOAH_SMTP_HOST"))
    SMTP_PORT: int = Field(587, validation_alias=AliasChoices("NOAH_SMTP_PORT"))
    SMTP_USER: str = Field("", validation_alias=AliasChoices("NOAH_SMTP_USER"))
    SMTP_PASSWORD: str = Field(
        "", validation_alias=AliasChoices("NOAH_SMTP_PASSWORD"))
    SMTP_FROM: str = Field(
        "", validation_alias=AliasChoices("NOAH_SMTP_FROM"))
    SMTP_TO: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("NOAH_SMTP_TO"))
    # Generic webhook (e.g. Discord/Slack-compatible relay); empty disables
    WEBHOOK_URL: str = Field(
        "", validation_alias=AliasChoices("NOAH_WEBHOOK_URL"))

    @field_validator("CORS_ORIGINS", "TRUSTED_PROXIES", "SMTP_TO",
                     mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("RATE_LIMIT_ENABLED", "EARTHQUAKE_ENABLED",
                     "EARTHQUAKE_ALERT_ENABLED", "EARTHQUAKE_WS_ENABLED",
                     mode="before")
    @classmethod
    def _parse_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "off", "")
        return v


settings = Settings()
