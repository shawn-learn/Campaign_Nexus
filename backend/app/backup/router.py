from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backup import service
from app.core.db import get_session

router = APIRouter(prefix="/api/v1/backups", tags=["backup"])


class BackupOut(BaseModel):
    id: str
    reason: str
    created_at: str
    db_bytes: int
    media_files: int


class CreateBackup(BaseModel):
    reason: str = "manual"


def _out(info: service.BackupInfo) -> BackupOut:
    return BackupOut(
        id=info.id, reason=info.reason, created_at=info.created_at,
        db_bytes=info.db_bytes, media_files=info.media_files,
    )


@router.get("", response_model=list[BackupOut])
def list_backups() -> list[BackupOut]:
    return [_out(i) for i in service.list_backups()]


@router.post("", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def create_backup(
    body: CreateBackup, session: Session = Depends(get_session)
) -> BackupOut:
    try:
        return _out(service.create_backup(session, reason=body.reason))
    except service.BackupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
