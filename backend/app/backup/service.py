"""Backup creation, listing, rotation and restore (docs/13 §7).

The SQLite database is snapshotted with ``VACUUM INTO``, which writes a consistent copy even
while the app holds the database open — so a backup can be taken mid-session without stopping
anything. The media tree is copied alongside it. A ``manifest.json`` records what and when.

Restore cannot hot-swap a database the app has open, so it is a stop-the-world operation:
``restore_backup`` copies the snapshot over the live paths and is meant to be run by
``scripts.restore_backup`` while the server is down (documented in SECURITY.md).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

MANIFEST_NAME = "manifest.json"
DB_NAME = "campaign_nexus.db"
MEDIA_DIRNAME = "media"
_SAFE = re.compile(r"[^a-z0-9]+")
BACKUP_VERSION = 1


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupInfo:
    id: str
    reason: str
    created_at: str
    db_bytes: int
    media_files: int
    path: str


def _settings() -> Settings:
    return get_settings()


def _db_path(settings: Settings) -> Path:
    """The on-disk SQLite file behind ``database_url`` (only file-backed DBs are snapshotted)."""
    url = settings.database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise BackupError(f"only file-backed SQLite can be snapshotted, not {url!r}")
    return Path(url[len(prefix):])


def _slug(reason: str) -> str:
    return _SAFE.sub("-", reason.lower()).strip("-") or "manual"


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
def create_backup(session: Session, *, reason: str = "manual") -> BackupInfo:
    """Snapshot the DB (via ``VACUUM INTO``) and the media tree into a new backup dir."""
    settings = _settings()
    _db_path(settings)  # validates the URL is file-backed before we do any work

    created = datetime.now(UTC)
    backup_id = f"{created.strftime('%Y%m%dT%H%M%SZ')}_{_slug(reason)}"
    root = Path(settings.backup_dir) / backup_id
    if root.exists():  # pragma: no cover - one-second collision
        raise BackupError(f"backup {backup_id} already exists")
    root.mkdir(parents=True)

    # VACUUM INTO needs a path SQLite can create; a forward-slashed absolute path is safest.
    db_dest = root / DB_NAME
    session.execute(text("VACUUM INTO :dest").bindparams(dest=db_dest.as_posix()))
    session.commit()

    media_files = 0
    media_src = Path(settings.media_dir)
    if media_src.exists():
        media_dest = root / MEDIA_DIRNAME
        shutil.copytree(media_src, media_dest)
        media_files = sum(1 for p in media_dest.rglob("*") if p.is_file())

    info = BackupInfo(
        id=backup_id, reason=reason, created_at=created.isoformat(),
        db_bytes=db_dest.stat().st_size, media_files=media_files, path=str(root),
    )
    (root / MANIFEST_NAME).write_text(json.dumps({
        "version": BACKUP_VERSION, "id": info.id, "reason": reason,
        "created_at": info.created_at, "db_bytes": info.db_bytes,
        "media_files": media_files,
    }, indent=2))

    prune_backups()
    return info


# --------------------------------------------------------------------------- #
# List / rotate
# --------------------------------------------------------------------------- #
def _read_manifest(root: Path) -> BackupInfo | None:
    manifest = root / MANIFEST_NAME
    if not manifest.is_dir() and manifest.exists():
        try:
            data = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            return None
        return BackupInfo(
            id=str(data.get("id", root.name)), reason=str(data.get("reason", "")),
            created_at=str(data.get("created_at", "")),
            db_bytes=int(data.get("db_bytes", 0)),
            media_files=int(data.get("media_files", 0)), path=str(root),
        )
    return None


def list_backups() -> list[BackupInfo]:
    """Newest first. Backup ids are timestamp-prefixed, so a name sort is a time sort."""
    base = Path(_settings().backup_dir)
    if not base.exists():
        return []
    infos = [info for child in base.iterdir() if child.is_dir() and (info := _read_manifest(child))]
    return sorted(infos, key=lambda i: i.id, reverse=True)


def prune_backups(keep: int | None = None) -> list[str]:
    """Delete all but the newest ``keep`` backups. Returns the ids removed."""
    keep = _settings().backup_keep if keep is None else keep
    removed: list[str] = []
    for info in list_backups()[max(keep, 0):]:
        shutil.rmtree(info.path, ignore_errors=True)
        removed.append(info.id)
    return removed


# --------------------------------------------------------------------------- #
# Restore (offline — see scripts.restore_backup)
# --------------------------------------------------------------------------- #
def restore_backup(backup_id: str) -> BackupInfo:
    """Copy a snapshot over the live DB and media paths. **The server must be stopped.**"""
    settings = _settings()
    root = Path(settings.backup_dir) / backup_id
    info = _read_manifest(root)
    if info is None:
        raise BackupError(f"no such backup: {backup_id}")

    db_src = root / DB_NAME
    if not db_src.exists():
        raise BackupError(f"backup {backup_id} has no database file")
    db_dest = _db_path(settings)
    db_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_src, db_dest)
    # A stale WAL/SHM would shadow the restored file; clear them.
    for suffix in ("-wal", "-shm"):
        sidecar = db_dest.with_name(db_dest.name + suffix)
        sidecar.unlink(missing_ok=True)

    media_src = root / MEDIA_DIRNAME
    media_dest = Path(settings.media_dir)
    if media_src.exists():
        if media_dest.exists():
            shutil.rmtree(media_dest)
        shutil.copytree(media_src, media_dest)

    return info
