from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.playbook import combat, dashboard, encounters, quests, service, travel
from app.modules.playbook.models import CombatRun
from app.modules.playbook.schemas import (
    AddMember,
    CombatActionIn,
    CombatRunOut,
    CombatSummary,
    DashboardOut,
    DependencyIn,
    EncounterCreate,
    EncounterOut,
    EncounterUpdate,
    ObjectiveToggle,
    PartyOut,
    PartyPatch,
    QuestCreate,
    QuestGraph,
    QuestOut,
    QuestStatusIn,
    QuestUpdate,
    RestRequest,
    RestResult,
    SetLocation,
    SetPin,
    StartCombat,
    TravelPlan,
    TravelRequest,
    TravelResult,
)
from app.modules.wiki.service import LinkCycle

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/party", tags=["party"])
encounters_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/encounters", tags=["encounters"]
)
combat_router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/combats", tags=["combat"])
quests_router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/quests", tags=["quests"])
views_router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/views", tags=["views"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


@router.get("", response_model=PartyOut)
def get_party(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> PartyOut:
    return service.to_out(session, service.get_or_create_party(session, ctx.campaign_id))


@router.patch("", response_model=PartyOut)
def patch_party(
    body: PartyPatch,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> PartyOut:
    if body.gold is not None:
        service.set_gold(session, ctx.campaign_id, body.gold)
    return service.to_out(session, service.get_or_create_party(session, ctx.campaign_id))


@router.post("/members", response_model=PartyOut)
def add_member(
    body: AddMember,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> PartyOut:
    try:
        party = service.add_member(
            session, ctx.campaign_id, body.stat_block_id, body.hit_points
        )
    except service.PlaybookError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return service.to_out(session, party)


@router.delete("/members/{stat_block_id}", response_model=PartyOut)
def remove_member(
    stat_block_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> PartyOut:
    party = service.remove_member(session, ctx.campaign_id, stat_block_id)
    return service.to_out(session, party)


@router.post("/rest", response_model=RestResult)
def rest(
    body: RestRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> RestResult:
    try:
        return service.rest(session, ctx.campaign_id, body.rest_type)
    except service.PlaybookError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


# --------------------------------------------------------------------------- #
# Travel (FR-5.3) — preview then commit, so the GM sees what fires en route
# --------------------------------------------------------------------------- #
def _travel_errors(exc: Exception) -> HTTPException:
    code = (
        status.HTTP_501_NOT_IMPLEMENTED
        if isinstance(exc, travel.TravelUnsupported)
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(code, str(exc))


@router.post("/travel/preview", response_model=TravelPlan)
def preview_travel(
    body: TravelRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> TravelPlan:
    try:
        return travel.plan(session, _campaign(session, ctx.campaign_id), body)
    except (travel.TravelError, travel.TravelUnsupported) as exc:
        raise _travel_errors(exc) from exc


@router.post("/travel", response_model=TravelResult)
def commit_travel(
    body: TravelRequest,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> TravelResult:
    try:
        return travel.commit(session, _campaign(session, ctx.campaign_id), body)
    except (travel.TravelError, travel.TravelUnsupported) as exc:
        raise _travel_errors(exc) from exc


# --------------------------------------------------------------------------- #
# Encounters
# --------------------------------------------------------------------------- #
@encounters_router.get("", response_model=list[EncounterOut])
def list_encounters(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[EncounterOut]:
    return encounters.list_encounters(session, _campaign(session, ctx.campaign_id))


@encounters_router.post("", response_model=EncounterOut, status_code=status.HTTP_201_CREATED)
def create_encounter(
    body: EncounterCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EncounterOut:
    return encounters.create_encounter(
        session, _campaign(session, ctx.campaign_id),
        name=body.name, terrain=body.terrain, hazards=body.hazards, tactics=body.tactics,
        combatants=body.combatants, location_id=body.location_id, created_by=ctx.user_id,
    )


@encounters_router.get("/{encounter_id}", response_model=EncounterOut)
def get_encounter(
    encounter_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> EncounterOut:
    try:
        return encounters.get_encounter(session, _campaign(session, ctx.campaign_id), encounter_id)
    except encounters.EncounterNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "encounter not found") from exc


# --------------------------------------------------------------------------- #
# Combat runs (event-sourced, ADR-005)
# --------------------------------------------------------------------------- #
def _run_out(session: Session, run: CombatRun) -> CombatRunOut:
    total = combat._total_actions(session, run.id)
    return CombatRunOut(
        run_id=run.id, encounter_id=run.encounter_id, status=run.status,
        cursor=run.fold_cursor, total_actions=total,
        can_undo=run.fold_cursor > 0, can_redo=run.fold_cursor < total,
        state=combat.state_of(session, run),
    )


@combat_router.post("", response_model=CombatRunOut, status_code=status.HTTP_201_CREATED)
def start_combat(
    body: StartCombat,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    run = combat.start_combat(session, _campaign(session, ctx.campaign_id), body.encounter_id)
    return _run_out(session, run)


def _load_run(session: Session, campaign_id: str, run_id: str) -> CombatRun:
    try:
        return combat._require(session, campaign_id, run_id)
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc


@combat_router.get("/{run_id}", response_model=CombatRunOut)
def get_combat(
    run_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> CombatRunOut:
    return _run_out(session, _load_run(session, ctx.campaign_id, run_id))


@combat_router.post("/{run_id}/actions", response_model=CombatRunOut)
def post_action(
    run_id: str,
    body: CombatActionIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    try:
        run = combat.append_action(session, ctx.campaign_id, run_id, body.action_type, body.payload)
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return _run_out(session, run)


@combat_router.post("/{run_id}/undo", response_model=CombatRunOut)
def undo(
    run_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Editor
) -> CombatRunOut:
    return _run_out(session, combat.undo(session, ctx.campaign_id, run_id))


@combat_router.post("/{run_id}/redo", response_model=CombatRunOut)
def redo(
    run_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Editor
) -> CombatRunOut:
    return _run_out(session, combat.redo(session, ctx.campaign_id, run_id))


@combat_router.post("/{run_id}/end", response_model=CombatSummary)
def end_combat(
    run_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatSummary:
    try:
        return combat.end_combat(session, _campaign(session, ctx.campaign_id), run_id)
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc


# --------------------------------------------------------------------------- #
# Quests (FR-10). Static paths are declared before /{quest_id} so they win the match.
# --------------------------------------------------------------------------- #
def _quest_404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "quest not found")


@quests_router.get("", response_model=list[QuestOut])
def list_quests(
    status_filter: str | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[QuestOut]:
    return quests.list_quests(session, _campaign(session, ctx.campaign_id), status=status_filter)


@quests_router.post("", response_model=QuestOut, status_code=status.HTTP_201_CREATED)
def create_quest(
    body: QuestCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        return quests.create_quest(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except quests.QuestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@quests_router.get("/graph", response_model=QuestGraph)
def quest_graph(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> QuestGraph:
    return quests.graph(session, _campaign(session, ctx.campaign_id))


@quests_router.get("/{quest_id}", response_model=QuestOut)
def get_quest(
    quest_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> QuestOut:
    try:
        return quests.get_quest(session, _campaign(session, ctx.campaign_id), quest_id)
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc


@quests_router.patch("/{quest_id}", response_model=QuestOut)
def update_quest(
    quest_id: str,
    body: QuestUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        return quests.update_quest(session, _campaign(session, ctx.campaign_id), quest_id, body)
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc
    except quests.QuestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@quests_router.post("/{quest_id}/status", response_model=QuestOut)
def set_quest_status(
    quest_id: str,
    body: QuestStatusIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        campaign = _campaign(session, ctx.campaign_id)
        return quests.set_status(session, campaign, quest_id, body.status)
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc
    except quests.InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except quests.QuestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@quests_router.post("/{quest_id}/objectives", response_model=QuestOut)
def toggle_objective(
    quest_id: str,
    body: ObjectiveToggle,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        return quests.toggle_objective(
            session, _campaign(session, ctx.campaign_id), quest_id, body.index, body.done
        )
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc
    except quests.QuestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@quests_router.post("/{quest_id}/dependencies", response_model=QuestOut)
def add_dependency(
    quest_id: str,
    body: DependencyIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        return quests.add_dependency(
            session, _campaign(session, ctx.campaign_id), quest_id, body.depends_on_id
        )
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc
    except LinkCycle as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@quests_router.delete("/{quest_id}/dependencies/{depends_on_id}", response_model=QuestOut)
def remove_dependency(
    quest_id: str,
    depends_on_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> QuestOut:
    try:
        return quests.remove_dependency(
            session, _campaign(session, ctx.campaign_id), quest_id, depends_on_id
        )
    except quests.QuestNotFound as exc:
        raise _quest_404(exc) from exc


# --------------------------------------------------------------------------- #
# Live session dashboard (FR-14) — one composite read + its UI-state setters
# --------------------------------------------------------------------------- #
@views_router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> DashboardOut:
    return dashboard.build(session, _campaign(session, ctx.campaign_id))


@views_router.put("/dashboard/location", response_model=DashboardOut)
def set_dashboard_location(
    body: SetLocation,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> DashboardOut:
    campaign = _campaign(session, ctx.campaign_id)
    try:
        dashboard.set_current_location(session, campaign, body.entity_id)
    except dashboard.DashboardError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return dashboard.build(session, campaign)


@views_router.put("/dashboard/pins", response_model=DashboardOut)
def set_dashboard_pin(
    body: SetPin,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> DashboardOut:
    campaign = _campaign(session, ctx.campaign_id)
    try:
        dashboard.set_pin(session, campaign, body.entity_id, body.pinned)
    except dashboard.DashboardError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return dashboard.build(session, campaign)


@encounters_router.patch("/{encounter_id}", response_model=EncounterOut)
def update_encounter(
    encounter_id: str,
    body: EncounterUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EncounterOut:
    try:
        return encounters.update_encounter(
            session, _campaign(session, ctx.campaign_id), encounter_id,
            terrain=body.terrain, hazards=body.hazards, tactics=body.tactics,
            combatants=body.combatants,
        )
    except encounters.EncounterNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "encounter not found") from exc
