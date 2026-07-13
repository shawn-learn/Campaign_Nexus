from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.story import service
from app.modules.story.schemas import (
    ConditionCheck,
    ConditionCheckIn,
    NodeStatusResult,
    SetFlagIn,
    StoryEdgeIn,
    StoryEdgeOut,
    StoryGraphOut,
    StoryNodeIn,
    StoryNodeOut,
    StoryNodeUpdate,
    StoryStatusIn,
    Suggestion,
)

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/story", tags=["story"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "not found")


@router.get("/graph", response_model=StoryGraphOut)
def get_graph(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> StoryGraphOut:
    return service.graph(session, _campaign(session, ctx.campaign_id))


@router.get("/suggestions", response_model=list[Suggestion])
def get_suggestions(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[Suggestion]:
    return service.suggestions(session, _campaign(session, ctx.campaign_id))


@router.post("/conditions/check", response_model=ConditionCheck)
def check_condition(
    body: ConditionCheckIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> ConditionCheck:
    return service.check_condition(session, _campaign(session, ctx.campaign_id), body.expr)


@router.put("/flags", response_model=dict)
def set_flag(
    body: SetFlagIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> dict[str, Any]:
    return service.set_flag(session, _campaign(session, ctx.campaign_id), body.key, body.value)


@router.post("/nodes", response_model=StoryNodeOut, status_code=status.HTTP_201_CREATED)
def create_node(
    body: StoryNodeIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> StoryNodeOut:
    try:
        return service.create_node(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except service.StoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.patch("/nodes/{node_id}", response_model=StoryNodeOut)
def update_node(
    node_id: str,
    body: StoryNodeUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> StoryNodeOut:
    try:
        return service.update_node(session, _campaign(session, ctx.campaign_id), node_id, body)
    except service.StoryNotFound as exc:
        raise _404(exc) from exc
    except service.StoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/nodes/{node_id}/status", response_model=NodeStatusResult)
def set_node_status(
    node_id: str,
    body: StoryStatusIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> NodeStatusResult:
    try:
        return service.set_node_status(
            session, _campaign(session, ctx.campaign_id), node_id, body.status
        )
    except service.StoryNotFound as exc:
        raise _404(exc) from exc
    except service.InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.StoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    node_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_node(session, _campaign(session, ctx.campaign_id), node_id)
    except service.StoryNotFound as exc:
        raise _404(exc) from exc


@router.post("/edges", response_model=StoryEdgeOut, status_code=status.HTTP_201_CREATED)
def create_edge(
    body: StoryEdgeIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> StoryEdgeOut:
    try:
        return service.create_edge(session, _campaign(session, ctx.campaign_id), body)
    except service.StoryNotFound as exc:
        raise _404(exc) from exc
    except service.StoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(
    edge_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_edge(session, _campaign(session, ctx.campaign_id), edge_id)
    except service.StoryNotFound as exc:
        raise _404(exc) from exc
