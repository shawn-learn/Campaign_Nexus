from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.archive import service
from app.core.db import get_session
from app.modules.campaign import service as campaign_service
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.campaign.schemas import CampaignOut

router = APIRouter(prefix="/api/v1", tags=["archive"])


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(
    session: Session = Depends(get_session),
    ctx: CampaignContext = Depends(require_campaign_role("viewer")),
) -> dict[str, Any]:
    campaign = session.get(Campaign, ctx.campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return service.export_campaign(session, campaign)


@router.post("/campaigns/import", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def import_campaign(
    archive: dict[str, Any],
    session: Session = Depends(get_session),
) -> CampaignOut:
    owner_id = campaign_service.get_local_user_id(session)
    try:
        campaign = service.import_campaign(session, archive, owner_user_id=owner_id)
    except (service.BadArchive, KeyError, ValueError, TypeError) as exc:
        # A structurally-wrong archive surfaces deep in the importer as a missing key,
        # a bad base64/JSON decode, or an unrecognized image — all subclasses of the
        # above. Turn them into a clean 422 instead of a 500. (ValueError covers
        # BadArchive, BadImage, json.JSONDecodeError, and binascii.Error.)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid campaign archive: {exc}"
        ) from exc
    return CampaignOut.model_validate(campaign)
