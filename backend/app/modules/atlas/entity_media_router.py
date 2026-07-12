"""Entity image attachments — a gallery of images on any wiki entity.

Reuses the atlas media store (content-addressed on disk). Lives in the atlas module because
that's where media storage and image validation live; the wiki module can't import atlas
(atlas already imports wiki).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.atlas import imagesize, service
from app.modules.atlas.schemas import AttachmentOut
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign

router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/entities/{entity_id}/media", tags=["atlas"]
)

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))

_MAX_BYTES = 32 * 1024 * 1024  # 32 MB — matches map upload cap


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


@router.get("", response_model=list[AttachmentOut])
def list_attachments(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[AttachmentOut]:
    return service.list_attachments(session, ctx.campaign_id, entity_id)


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    entity_id: str,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> AttachmentOut:
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image too large (max 32 MB)")
    try:
        imagesize.sniff(data)  # validate before touching disk
        return service.attach_media(
            session, _campaign(session, ctx.campaign_id), entity_id,
            data=data, filename=file.filename or "image", caption=caption,
        )
    except imagesize.BadImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except service.EntityNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entity not found") from exc


@router.get("/{attachment_id}/image")
def get_attachment_image(
    entity_id: str,
    attachment_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> FileResponse:
    try:
        media = service.media_for_attachment(session, ctx.campaign_id, entity_id, attachment_id)
    except service.AttachmentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found") from exc
    path = service.media_abspath(media)
    if not path.exists():  # pragma: no cover - disk/db drift
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image file missing")
    # Content-addressed name → safe to cache aggressively.
    return FileResponse(
        path, media_type=media.mime,
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    entity_id: str,
    attachment_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_attachment(session, ctx.campaign_id, entity_id, attachment_id)
    except service.AttachmentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found") from exc
