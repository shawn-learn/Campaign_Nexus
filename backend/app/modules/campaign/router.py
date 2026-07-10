from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign import service
from app.modules.campaign.schemas import CampaignCreate, CampaignOut

router = APIRouter(prefix="/api/v1", tags=["campaigns"])


@router.get("/campaigns", response_model=list[CampaignOut])
def get_campaigns(session: Session = Depends(get_session)) -> list[CampaignOut]:
    return [CampaignOut.model_validate(c) for c in service.list_campaigns(session)]


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def post_campaign(
    body: CampaignCreate, session: Session = Depends(get_session)
) -> CampaignOut:
    created_by = service.get_local_user_id(session)
    try:
        campaign = service.create_campaign(
            session,
            name=body.name,
            description=body.description,
            rule_system_id=body.rule_system_id,
            created_by=created_by,
        )
    except service.UnknownRuleSystem as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown rule_system_id: {exc}"
        ) from exc
    return CampaignOut.model_validate(campaign)
