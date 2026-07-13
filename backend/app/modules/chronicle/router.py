from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_session
from app.core.domain_event import DomainEvent
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.chronicle import service
from app.modules.time import service as time_service
from app.modules.time.schemas import ClockOut
from app.modules.chronicle.schemas import (
    ManualEntryCreate,
    NoteCreate,
    SessionCreate,
    SessionDetail,
    SessionEntityRef,
    SessionEvent,
    SessionOut,
    TimelineEntryOut,
    TimelineEntryPatch,
)

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}", tags=["chronicle"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


# --------------------------------------------------------------------------- #
# Raw event log (kept from Sprint 1)
# --------------------------------------------------------------------------- #
class EventOut(BaseModel):
    id: str
    seq: int
    event_type: str
    occurred_at_game: int
    recorded_at_real: str
    actor: str
    narrative_text: str
    payload: dict[str, object]


@router.get("/events", response_model=list[EventOut])
def get_events(
    limit: int = 100,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[EventOut]:
    rows = session.scalars(
        select(DomainEvent)
        .where(DomainEvent.campaign_id == ctx.campaign_id)
        .order_by(DomainEvent.seq.desc())
        .limit(min(limit, 500))
    )
    return [
        EventOut(
            id=r.id, seq=r.seq, event_type=r.event_type, occurred_at_game=r.occurred_at_game,
            recorded_at_real=r.recorded_at_real, actor=r.actor, narrative_text=r.narrative_text,
            payload=json.loads(r.payload_json),
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
@router.get("/timeline", response_model=list[TimelineEntryOut])
def get_timeline(
    session_id: str | None = None,
    entity_id: str | None = None,
    from_game: int | None = None,
    to_game: int | None = None,
    significance_min: int | None = None,
    include_hidden: bool = False,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[TimelineEntryOut]:
    entries = service.query_timeline(
        session, ctx.campaign_id, session_id=session_id, entity_id=entity_id,
        from_game=from_game, to_game=to_game, significance_min=significance_min,
        include_hidden=include_hidden,
    )
    return [TimelineEntryOut.model_validate(e) for e in entries]


@router.post("/timeline/manual", response_model=TimelineEntryOut, status_code=201)
def post_manual_entry(
    body: ManualEntryCreate,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> TimelineEntryOut:
    entry = service.create_manual_entry(
        session, ctx.campaign_id, title=body.title, body=body.body,
        occurred_at_game=body.occurred_at_game, icon=body.icon,
        significance=body.significance, entity_ids=body.entity_ids,
    )
    return TimelineEntryOut.model_validate(entry)


@router.post("/timeline/clear", response_model=ClockOut)
def clear_timeline(
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ClockOut:
    """Wipe the whole timeline and reset the clock back to the campaign's start time."""
    campaign = session.get(Campaign, ctx.campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    service.clear_timeline(session, ctx.campaign_id)
    return time_service.set_clock(
        session,
        campaign,
        time_game=campaign.campaign_start_game,
        reason="timeline cleared",
        set_as_start=False,
    )


@router.patch("/timeline/{entry_id}", response_model=TimelineEntryOut)
def patch_entry(
    entry_id: str,
    body: TimelineEntryPatch,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> TimelineEntryOut:
    try:
        entry = service.set_hidden(session, ctx.campaign_id, entry_id, body.is_hidden)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "timeline entry not found") from exc
    return TimelineEntryOut.model_validate(entry)


@router.delete("/timeline/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: str,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_manual_entry(session, ctx.campaign_id, entry_id)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "timeline entry not found") from exc
    except service.SessionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
@router.get("/sessions", response_model=list[SessionOut])
def get_sessions(
    session: DbSession = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in service.list_sessions(session, ctx.campaign_id)]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def post_session(
    body: SessionCreate,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SessionOut:
    sess = service.create_session(
        session, ctx.campaign_id, real_date=body.real_date, summary=body.summary
    )
    return SessionOut.model_validate(sess)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session_detail(
    session_id: str,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> SessionDetail:
    try:
        sess = service._require_session(session, ctx.campaign_id, session_id)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    events = [
        SessionEvent(
            event_type=e.event_type, occurred_at_game=e.occurred_at_game,
            narrative_text=e.narrative_text,
        )
        for e in service.session_events(session, session_id)
    ]
    entities = [SessionEntityRef(**r) for r in service.session_entities(session, session_id)]
    detail = SessionDetail.model_validate(sess)
    detail.events = events
    detail.entities = entities
    return detail


@router.post("/sessions/{session_id}/start", response_model=SessionOut)
def start_session(
    session_id: str,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SessionOut:
    try:
        return SessionOut.model_validate(
            service.start_session(session, ctx.campaign_id, session_id)
        )
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    except service.SessionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(
    session_id: str,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SessionOut:
    try:
        return SessionOut.model_validate(
            service.end_session(session, ctx.campaign_id, session_id)
        )
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    except service.SessionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


# --------------------------------------------------------------------------- #
# Quick notes
# --------------------------------------------------------------------------- #
@router.post("/notes", status_code=status.HTTP_204_NO_CONTENT)
def post_note(
    body: NoteCreate,
    session: DbSession = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    service.capture_note(session, ctx.campaign_id, body.text, body.entity_ids)
