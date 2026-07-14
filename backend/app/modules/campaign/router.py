from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.pipeline import command_tx
from app.modules.campaign import service
from app.modules.campaign.cos_weather import roll_weather
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.campaign.schemas import CampaignCreate, CampaignOut

router = APIRouter(prefix="/api/v1", tags=["campaigns"])

Editor = Depends(require_campaign_role("editor"))


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
            calendar_id=body.calendar_id,
        )
    except service.UnknownRuleSystem as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown rule_system_id: {exc}"
        ) from exc
    return CampaignOut.model_validate(campaign)


@router.post("/campaigns/{campaign_id}/weather/roll", response_model=dict)
def post_roll_weather(
    campaign_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> dict[str, Any]:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
        
    with command_tx(session, campaign_id, actor="gm") as cmd_ctx:
        at_game_time = campaign.clock_time_game
        result = roll_weather(session, cmd_ctx, campaign_id, at_game_time)
        
    return result

