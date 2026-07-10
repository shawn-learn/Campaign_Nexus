"""Application configuration (12-factor via environment / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ project root (this file is app/core/config.py)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Campaign Nexus"
    environment: str = "local"

    # SQLite lives beside the backend by default; override with NEXUS_DATABASE_URL.
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'campaign_nexus.db').as_posix()}"

    # Uploaded media (map images, handouts) — content-addressed files beside the DB.
    media_dir: Path = BACKEND_ROOT / "media"

    # Automatic DB+media snapshots (docs/13 §7). Rotation keeps the newest ``backup_keep``.
    backup_dir: Path = BACKEND_ROOT / "backups"
    backup_keep: int = 10

    # Bind localhost only in the local-first posture (docs/11-security-model.md, P-Local).
    host: str = "127.0.0.1"
    port: int = 8000

    # Comma-free list is fine for the single-origin dev frontend.
    cors_origins: tuple[str, ...] = ("http://localhost:5200",)


@lru_cache
def get_settings() -> Settings:
    return Settings()
