from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.chronicle.models import Session as GameSession
from app.modules.npcs import service
from app.modules.npcs.schemas import (
    HistoryRow,
    InteractionIn,
    NpcCreate,
    NpcOut,
    NpcUpdate,
    RelocateIn,
    ScheduleCreate,
    ScheduleOut,
    StatusIn,
    WhereOut,
)

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/npcs", tags=["npcs"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "npc not found")


@router.get("", response_model=list[NpcOut])
def list_npcs(
    status_filter: str | None = Query(default=None, alias="status"),
    location_id: str | None = None,
    faction_id: str | None = None,
    met_party: bool | None = None,
    knows: str | None = None,
    include_deleted: bool = False,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[NpcOut]:
    """The saved queries (FR-6.6): by status, location, faction, met-party, knows-X."""
    return service.list_npcs(
        session, ctx.campaign_id, status=status_filter, location_id=location_id,
        faction_id=faction_id, met_party=met_party, knows=knows,
        include_deleted=include_deleted,
    )


@router.post("", response_model=NpcOut, status_code=status.HTTP_201_CREATED)
def create_npc(
    body: NpcCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NpcOut:
    try:
        return service.create_npc(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except service.NpcError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/schedules", response_model=list[ScheduleOut])
def list_all_schedules(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[ScheduleOut]:
    return service.list_schedules(session, ctx.campaign_id)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_schedule(session, ctx.campaign_id, schedule_id)
    except service.NpcNotFound as exc:
        raise _404(exc) from exc


@router.get("/{npc_id}", response_model=NpcOut)
def get_npc(
    npc_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> NpcOut:
    try:
        return service.get_npc(session, ctx.campaign_id, npc_id)
    except service.NpcNotFound as exc:
        raise _404(exc) from exc


@router.patch("/{npc_id}", response_model=NpcOut)
def update_npc(
    npc_id: str,
    body: NpcUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NpcOut:
    try:
        return service.update_npc(session, ctx.campaign_id, npc_id, body)
    except service.NpcNotFound as exc:
        raise _404(exc) from exc


@router.post("/{npc_id}/relocate", response_model=NpcOut)
def relocate(
    npc_id: str,
    body: RelocateIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NpcOut:
    try:
        return service.relocate(
            session, _campaign(session, ctx.campaign_id), npc_id, body.location_id,
            reason=body.reason,
        )
    except service.NpcNotFound as exc:
        raise _404(exc) from exc
    except service.NpcError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/{npc_id}/status", response_model=NpcOut)
def set_status(
    npc_id: str,
    body: StatusIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NpcOut:
    try:
        return service.set_status(
            session, _campaign(session, ctx.campaign_id), npc_id, body.status, body.reason
        )
    except service.NpcNotFound as exc:
        raise _404(exc) from exc
    except service.NpcError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/{npc_id}/interactions", response_model=NpcOut)
def record_interaction(
    npc_id: str,
    body: InteractionIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NpcOut:
    try:
        return service.record_interaction(
            session, _campaign(session, ctx.campaign_id), npc_id, body.summary
        )
    except service.NpcNotFound as exc:
        raise _404(exc) from exc


@router.get("/{npc_id}/history", response_model=list[HistoryRow])
def get_history(
    npc_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[HistoryRow]:
    try:
        return service.history(session, _campaign(session, ctx.campaign_id), npc_id)
    except service.NpcNotFound as exc:
        raise _404(exc) from exc


@router.get("/{npc_id}/where", response_model=WhereOut)
def where_was(
    npc_id: str,
    at_game: int | None = None,
    session_id: str | None = None,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> WhereOut:
    """"Where is X now / where was X at time T / where was X during session N" (FR-6.2).

    A session is a *span* of campaign time, so it answers with every place the NPC occupied
    while it ran; an instant answers with exactly one.
    """
    campaign = _campaign(session, ctx.campaign_id)
    window: tuple[int, int] | None = None
    if session_id is not None:
        game_session = session.get(GameSession, session_id)
        if game_session is None or game_session.campaign_id != campaign.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
        start = game_session.clock_start_game
        if start is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "session never started")
        window = (start, game_session.clock_end_game or campaign.clock_time_game)
    elif at_game is None:
        at_game = campaign.clock_time_game  # "where is X now"

    try:
        out = service.where_was(session, campaign, npc_id, at_game=at_game, window=window)
    except service.NpcNotFound as exc:
        raise _404(exc) from exc
    out.session_id = session_id
    return out


@router.get("/{npc_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(
    npc_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[ScheduleOut]:
    return service.list_schedules(session, ctx.campaign_id, npc_id)


@router.post("/{npc_id}/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    npc_id: str,
    body: ScheduleCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ScheduleOut:
    try:
        return service.create_schedule(
            session, _campaign(session, ctx.campaign_id), npc_id, body
        )
    except service.NpcNotFound as exc:
        raise _404(exc) from exc
    except service.NpcError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
