from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign import flags as campaign_flags
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.time import scheduled, service
from app.modules.time.schemas import (
    AdvancePreview,
    AdvanceReport,
    AdvanceRequest,
    ClockOut,
    RealtimeRequest,
    ScheduledEventCreate,
    ScheduledEventOut,
)

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}", tags=["time"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _load(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


def _delta(campaign: Campaign, body: AdvanceRequest) -> int:
    cal = service.calendar_for(campaign)
    return cal.to_seconds(
        days=body.days, hours=body.hours, minutes=body.minutes, seconds=body.seconds
    )


@router.get("/clock", response_model=ClockOut)
def get_clock(session: Session = Depends(get_session), ctx: CampaignContext = Viewer) -> ClockOut:
    # Reading the clock banks any elapsed real time, so it visibly ticks forward.
    return service.read_clock(session, _load(session, ctx.campaign_id))


@router.post("/clock/realtime", response_model=ClockOut)
def set_realtime(
    body: RealtimeRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ClockOut:
    return service.set_realtime(session, _load(session, ctx.campaign_id), body.enabled)


@router.post("/clock/advance", response_model=AdvanceReport)
def advance(
    body: AdvanceRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> AdvanceReport:
    campaign = _load(session, ctx.campaign_id)
    try:
        return service.advance_time(
            session, campaign, delta_seconds=_delta(campaign, body), reason=body.reason
        )
    except service.NoAdvance as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except scheduled.RunawayGuard as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/clock/advance/preview", response_model=AdvancePreview)
def advance_preview(
    body: AdvanceRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> AdvancePreview:
    campaign = _load(session, ctx.campaign_id)
    return service.preview_advance(session, campaign, delta_seconds=_delta(campaign, body))


@router.get("/scheduled-events", response_model=list[ScheduledEventOut])
def list_scheduled(
    status_filter: str | None = None,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[ScheduledEventOut]:
    cal = service.calendar_for(_load(session, ctx.campaign_id))
    events = scheduled.list_events(session, ctx.campaign_id, status=status_filter)
    return [scheduled.to_out(cal, e) for e in events]


@router.post(
    "/scheduled-events", response_model=ScheduledEventOut, status_code=status.HTTP_201_CREATED
)
def create_scheduled(
    body: ScheduledEventCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ScheduledEventOut:
    cal = service.calendar_for(_load(session, ctx.campaign_id))
    event = scheduled.create(session, ctx.campaign_id, body)
    return scheduled.to_out(cal, event)


@router.delete("/scheduled-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_scheduled(
    event_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    if not scheduled.cancel(session, ctx.campaign_id, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scheduled event not found")


@router.get("/flags")
def get_flags(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> dict[str, Any]:
    return campaign_flags.list_flags(session, ctx.campaign_id)
