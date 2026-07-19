from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.playbook import (
    combat,
    dashboard,
    encounters,
    quests,
    service,
    skill_challenges,
    tables,
    travel,
)
from app.modules.playbook.models import CombatRoll, CombatRun
from app.modules.playbook.schemas import (
    AddCombatantIn,
    AddMember,
    AttackIn,
    AttackOut,
    AttackResultOut,
    CombatActionIn,
    CombatRollOut,
    CombatRunBrief,
    CombatRunOut,
    CombatSummary,
    DashboardOut,
    DeathSaveIn,
    DeathSaveRulesOut,
    DependencyIn,
    EncounterCreate,
    EncounterOut,
    EncounterUpdate,
    LocationConnectionCreate,
    LocationConnectionOut,
    ObjectiveToggle,
    PartyOut,
    PartyPatch,
    QuestCreate,
    QuestGraph,
    QuestOut,
    QuestStatusIn,
    QuestUpdate,
    RandomTableCreate,
    RandomTableOut,
    RandomTableUpdate,
    RecordCheckIn,
    RestRequest,
    RestResult,
    RollDetail,
    RollInitiativeIn,
    RollOut,
    SetLocation,
    SetPin,
    SkillChallengeCreate,
    SkillChallengeOut,
    SkillChallengeRunOut,
    SkillChallengeUpdate,
    StartCombat,
    StartSkillRun,
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
skill_challenges_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/skill-challenges", tags=["skill-challenges"]
)
skill_runs_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/skill-runs", tags=["skill-challenges"]
)
tables_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/random-tables", tags=["random-tables"]
)
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
    party = service.patch_party(session, ctx.campaign_id, body)
    return service.to_out(session, party)


@router.get("/connections", response_model=list[LocationConnectionOut])
def list_connections(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[LocationConnectionOut]:
    return service.list_connections(session, ctx.campaign_id)


@router.post("/connections", response_model=LocationConnectionOut)
def create_connection(
    body: LocationConnectionCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> LocationConnectionOut:
    try:
        return service.upsert_connection(session, ctx.campaign_id, body)
    except service.PlaybookError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


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
# Skill challenges (FR-12) — system-agnostic non-combat scenes
# --------------------------------------------------------------------------- #
def _sc_404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "skill challenge not found")


@skill_challenges_router.get("", response_model=list[SkillChallengeOut])
def list_skill_challenges(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[SkillChallengeOut]:
    return skill_challenges.list_skill_challenges(
        session, _campaign(session, ctx.campaign_id)
    )


@skill_challenges_router.post(
    "", response_model=SkillChallengeOut, status_code=status.HTTP_201_CREATED
)
def create_skill_challenge(
    body: SkillChallengeCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SkillChallengeOut:
    return skill_challenges.create_skill_challenge(
        session, _campaign(session, ctx.campaign_id),
        name=body.name, premise=body.premise, total_checks=body.total_checks,
        success_target=body.success_target, failure_cap=body.failure_cap,
        approaches=body.approaches, outcomes=body.outcomes,
        location_id=body.location_id, created_by=ctx.user_id,
    )


@skill_challenges_router.get("/{challenge_id}", response_model=SkillChallengeOut)
def get_skill_challenge(
    challenge_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> SkillChallengeOut:
    try:
        return skill_challenges.get_skill_challenge(
            session, _campaign(session, ctx.campaign_id), challenge_id
        )
    except skill_challenges.SkillChallengeNotFound as exc:
        raise _sc_404(exc) from exc


@skill_challenges_router.patch("/{challenge_id}", response_model=SkillChallengeOut)
def update_skill_challenge(
    challenge_id: str,
    body: SkillChallengeUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SkillChallengeOut:
    try:
        return skill_challenges.update_skill_challenge(
            session, _campaign(session, ctx.campaign_id), challenge_id,
            premise=body.premise, total_checks=body.total_checks,
            success_target=body.success_target, failure_cap=body.failure_cap,
            approaches=body.approaches, outcomes=body.outcomes,
        )
    except skill_challenges.SkillChallengeNotFound as exc:
        raise _sc_404(exc) from exc


@skill_runs_router.post(
    "", response_model=SkillChallengeRunOut, status_code=status.HTTP_201_CREATED
)
def start_skill_run(
    body: StartSkillRun,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SkillChallengeRunOut:
    try:
        return skill_challenges.start_run(
            session, _campaign(session, ctx.campaign_id), body.challenge_id
        )
    except skill_challenges.SkillChallengeNotFound as exc:
        raise _sc_404(exc) from exc


@skill_runs_router.get("/{run_id}", response_model=SkillChallengeRunOut)
def get_skill_run(
    run_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> SkillChallengeRunOut:
    try:
        return skill_challenges.get_run(
            session, _campaign(session, ctx.campaign_id), run_id
        )
    except skill_challenges.SkillRunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill run not found") from exc


@skill_runs_router.post("/{run_id}/checks", response_model=SkillChallengeRunOut)
def record_skill_check(
    run_id: str,
    body: RecordCheckIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> SkillChallengeRunOut:
    try:
        return skill_challenges.record_check(
            session, _campaign(session, ctx.campaign_id), run_id, body
        )
    except skill_challenges.SkillRunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill run not found") from exc
    except skill_challenges.SkillRunClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "skill run already resolved") from exc


@skill_runs_router.post("/{run_id}/undo", response_model=SkillChallengeRunOut)
def undo_skill_check(
    run_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Editor
) -> SkillChallengeRunOut:
    try:
        return skill_challenges.undo_check(
            session, _campaign(session, ctx.campaign_id), run_id
        )
    except skill_challenges.SkillRunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill run not found") from exc


@skill_runs_router.post("/{run_id}/resolve", response_model=SkillChallengeRunOut)
def resolve_skill_run(
    run_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Editor
) -> SkillChallengeRunOut:
    try:
        return skill_challenges.resolve_run(
            session, _campaign(session, ctx.campaign_id), run_id
        )
    except skill_challenges.SkillRunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill run not found") from exc


# --------------------------------------------------------------------------- #
# Random tables (FR-12.x)
# --------------------------------------------------------------------------- #
def _table_404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "random table not found")


def _bad_dice(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid dice: {exc}")


def _invalid_table(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@tables_router.get("", response_model=list[RandomTableOut])
def list_random_tables(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[RandomTableOut]:
    return tables.list_random_tables(session, _campaign(session, ctx.campaign_id))


@tables_router.post("", response_model=RandomTableOut, status_code=status.HTTP_201_CREATED)
def create_random_table(
    body: RandomTableCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> RandomTableOut:
    try:
        return tables.create_random_table(
            session, _campaign(session, ctx.campaign_id),
            name=body.name, dice=body.dice, rows=body.rows, created_by=ctx.user_id,
        )
    except tables.BadDice as exc:
        raise _bad_dice(exc) from exc
    except tables.InvalidTable as exc:
        raise _invalid_table(exc) from exc


@tables_router.get("/{table_id}", response_model=RandomTableOut)
def get_random_table(
    table_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> RandomTableOut:
    try:
        return tables.get_random_table(session, _campaign(session, ctx.campaign_id), table_id)
    except tables.RandomTableNotFound as exc:
        raise _table_404(exc) from exc


@tables_router.patch("/{table_id}", response_model=RandomTableOut)
def update_random_table(
    table_id: str,
    body: RandomTableUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> RandomTableOut:
    try:
        return tables.update_random_table(
            session, _campaign(session, ctx.campaign_id), table_id,
            name=body.name, dice=body.dice, rows=body.rows,
        )
    except tables.RandomTableNotFound as exc:
        raise _table_404(exc) from exc
    except tables.BadDice as exc:
        raise _bad_dice(exc) from exc
    except tables.InvalidTable as exc:
        raise _invalid_table(exc) from exc


@tables_router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_random_table(
    table_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        tables.delete_random_table(session, _campaign(session, ctx.campaign_id), table_id)
    except tables.RandomTableNotFound as exc:
        raise _table_404(exc) from exc


@tables_router.post("/{table_id}/roll", response_model=RollOut)
def roll_random_table(
    table_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> RollOut:
    try:
        return tables.roll(session, _campaign(session, ctx.campaign_id), table_id)
    except tables.RandomTableNotFound as exc:
        raise _table_404(exc) from exc


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
        combatant_blocks=combat.combatant_blocks(session, run.id),
        initiative_dice=combat.initiative_die(session, run),
        death_saves=DeathSaveRulesOut.model_validate(combat.death_save_rules(session, run)),
    )


@combat_router.get("", response_model=list[CombatRunBrief])
def list_combats(
    encounter_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[CombatRunBrief]:
    # Unfiltered, this used to answer "[]", which left an in-play run reachable only
    # through whatever the browser had in localStorage — lose that and the campaign was
    # stuck in combat mode with no way back. Unfiltered now means the runs still in play.
    runs = (
        combat.runs_for_encounter(session, ctx.campaign_id, encounter_id)
        if encounter_id
        else combat.open_runs(session, ctx.campaign_id)
    )
    return [
        CombatRunBrief(
            run_id=r.id, encounter_id=r.encounter_id, status=r.status,
            round=combat.state_of(session, r).round,
        )
        for r in runs
    ]


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


@combat_router.post("/{run_id}/initiative", response_model=CombatRunOut)
def roll_initiative(
    run_id: str,
    body: RollInitiativeIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    """Roll for a scope and/or take the totals the GM typed in — one round trip for both."""
    try:
        run = combat.roll_initiative(
            session, _campaign(session, ctx.campaign_id), run_id,
            scope=body.scope, ids=body.ids, values=body.values, mode=body.mode,
        )
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return _run_out(session, run)


@combat_router.post("/{run_id}/combatants", response_model=CombatRunOut)
def add_combatant(
    run_id: str,
    body: AddCombatantIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    """Add a straggler mid-fight, seeded from the bestiary or entered by hand."""
    try:
        run = combat.add_combatant(
            session, _campaign(session, ctx.campaign_id), run_id,
            monster_id=body.monster_id, name=body.name, max_hp=body.max_hp,
            count=body.count, side=body.side, kind=body.kind, initiative=body.initiative,
        )
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatantNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "monster not found") from exc
    except combat.BadCombatant as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return _run_out(session, run)


@combat_router.post("/{run_id}/death-save", response_model=CombatRunOut)
def roll_death_save(
    run_id: str,
    body: DeathSaveIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    """Roll one death save. The rule system decides what the die means; this records it."""
    try:
        run = combat.roll_death_save(
            session, _campaign(session, ctx.campaign_id), run_id, body.combatant_id,
        )
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatantNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combatant not found") from exc
    except combat.BadCombatant as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return _run_out(session, run)


@combat_router.post("/{run_id}/begin", response_model=CombatRunOut)
def begin_combat(
    run_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> CombatRunOut:
    """Leave setup and start round 1."""
    try:
        run = combat.begin_combat(session, ctx.campaign_id, run_id)
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return _run_out(session, run)


def _roll_out(roll: CombatRoll) -> CombatRollOut:
    return CombatRollOut(
        id=roll.id, combatant_id=roll.combatant_id, kind=roll.kind, label=roll.label,
        expression=roll.expression, mode=roll.mode,
        detail=RollDetail.model_validate(json.loads(roll.detail_json)),
        total=roll.total, target=roll.target, outcome=roll.outcome,
        recorded_at_real=roll.recorded_at_real,
    )


@combat_router.get("/{run_id}/combatants/{combatant_id}/attacks", response_model=list[AttackOut])
def list_attacks(
    run_id: str,
    combatant_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[AttackOut]:
    """What this combatant can do, resolved by its rule system into plain numbers."""
    _load_run(session, ctx.campaign_id, run_id)
    return [
        AttackOut.model_validate(a)
        for a in combat.attacks_for(
            session, _campaign(session, ctx.campaign_id), run_id, combatant_id
        )
    ]


@combat_router.post("/{run_id}/attack", response_model=AttackResultOut)
def roll_attack(
    run_id: str,
    body: AttackIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> AttackResultOut:
    """Roll an attack and report the result. Applies nothing — that stays the GM's call."""
    try:
        result = combat.attack(
            session, _campaign(session, ctx.campaign_id), run_id,
            attacker_id=body.attacker_id, action_index=body.action_index,
            target_id=body.target_id, mode=body.mode,
        )
    except combat.CombatNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combat not found") from exc
    except combat.CombatantNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "combatant not found") from exc
    except combat.BadCombatant as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except combat.CombatClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "combat already ended") from exc
    return AttackResultOut(
        action_name=result["action_name"],
        attacker_id=result["attacker_id"],
        target_id=result["target_id"],
        target_ac=result["target_ac"],
        outcome=result["outcome"],
        to_hit=_roll_out(result["to_hit"]) if result["to_hit"] else None,
        damage=[_roll_out(r) for r in result["damage"]],
        total_damage=result["total_damage"],
        save=result["save"],
        description=result["description"],
    )


@combat_router.get("/{run_id}/rolls", response_model=list[CombatRollOut])
def list_rolls(
    run_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[CombatRollOut]:
    _load_run(session, ctx.campaign_id, run_id)
    return [_roll_out(r) for r in combat.rolls_for(session, run_id, limit)]


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


@combat_router.post("/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_combat(
    run_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    """Call the fight off — no summary, no write-back, back to exploration."""
    try:
        combat.cancel_combat(session, _campaign(session, ctx.campaign_id), run_id)
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
