from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.rules import bestiary, registry, service
from app.modules.rules.interface import RuleSystem, UnknownSheetType
from app.modules.rules.schemas import (
    ConditionOut,
    FacetDefOut,
    ImportResult,
    MonsterOut,
    RuleSystemInfo,
    StatBlockCreate,
    StatBlockOut,
    StatBlockUpdate,
    ValidateRequest,
    ValidateResult,
)

# Global (system metadata is not campaign-specific).
systems_router = APIRouter(prefix="/api/v1/rule-systems", tags=["rules"])
# Campaign-scoped stat blocks.
blocks_router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/stat-blocks", tags=["rules"])
# Campaign-scoped bestiary.
monsters_router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/monsters", tags=["rules"])


def _system_or_404(system_id: str) -> RuleSystem:
    try:
        return registry.get_system(system_id)
    except registry.UnknownRuleSystem as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule system not installed") from exc


@systems_router.get("", response_model=list[RuleSystemInfo])
def list_systems() -> list[RuleSystemInfo]:
    return [
        RuleSystemInfo(id=s.id, name=s.name, version=s.version, sheet_types=s.sheet_types())
        for s in registry.all_systems()
    ]


@systems_router.get("/{system_id}/schema/{sheet_type}")
def get_schema(system_id: str, sheet_type: str) -> dict[str, Any]:
    system = _system_or_404(system_id)
    try:
        return system.sheet_schema(sheet_type)
    except UnknownSheetType as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown sheet type") from exc


@systems_router.get("/{system_id}/layout/{sheet_type}")
def get_layout(system_id: str, sheet_type: str) -> dict[str, Any]:
    system = _system_or_404(system_id)
    try:
        return system.render_layout(sheet_type)
    except UnknownSheetType as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown sheet type") from exc


@systems_router.post("/{system_id}/validate", response_model=ValidateResult)
def validate_doc(system_id: str, body: ValidateRequest) -> ValidateResult:
    _system_or_404(system_id)
    errors, derived = service.validate_and_derive(system_id, body.sheet_type, body.doc)
    return ValidateResult(valid=not errors, errors=errors, derived=derived)


@systems_router.get("/{system_id}/facets", response_model=list[FacetDefOut])
def get_facets(system_id: str) -> list[FacetDefOut]:
    return [FacetDefOut(**f) for f in _system_or_404(system_id).facet_manifest()]


@systems_router.get("/{system_id}/conditions", response_model=list[ConditionOut])
def get_conditions(system_id: str) -> list[ConditionOut]:
    return [ConditionOut(**c) for c in _system_or_404(system_id).conditions()]


@systems_router.get("/{system_id}/travel")
def get_travel_table(system_id: str) -> dict[str, Any]:
    """Paces, conveyances and terrain multipliers — the travel planner's vocabulary."""
    return _system_or_404(system_id).travel_pace_table()


# --------------------------------------------------------------------------- #
# Stat blocks (campaign-scoped)
# --------------------------------------------------------------------------- #
Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


@blocks_router.get("", response_model=list[StatBlockOut])
def list_blocks(
    sheet_type: str | None = None,
    rule_system_id: str | None = None,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[StatBlockOut]:
    rows = service.list_stat_blocks(
        session, ctx.campaign_id, sheet_type=sheet_type, rule_system_id=rule_system_id
    )
    return [StatBlockOut.model_validate(r) for r in rows]


@blocks_router.post("", response_model=StatBlockOut, status_code=status.HTTP_201_CREATED)
def create_block(
    body: StatBlockCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> StatBlockOut:
    if not registry.has_system(body.rule_system_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule system not installed")
    try:
        row = service.create_stat_block(
            session, ctx.campaign_id, rule_system_id=body.rule_system_id,
            sheet_type=body.sheet_type, label=body.label, doc=body.doc,
        )
    except service.ValidationFailed as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": exc.errors}
        ) from exc
    return StatBlockOut.model_validate(row)


@blocks_router.get("/{block_id}", response_model=StatBlockOut)
def get_block(
    block_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> StatBlockOut:
    try:
        return StatBlockOut.model_validate(
            service.get_stat_block(session, ctx.campaign_id, block_id)
        )
    except service.StatBlockNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stat block not found") from exc


@blocks_router.put("/{block_id}", response_model=StatBlockOut)
def update_block(
    block_id: str,
    body: StatBlockUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> StatBlockOut:
    try:
        row = service.update_stat_block(
            session, ctx.campaign_id, block_id, label=body.label, doc=body.doc
        )
    except service.StatBlockNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stat block not found") from exc
    except service.ValidationFailed as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": exc.errors}
        ) from exc
    return StatBlockOut.model_validate(row)


# --------------------------------------------------------------------------- #
# Bestiary (campaign-scoped monsters)
# --------------------------------------------------------------------------- #
@monsters_router.get("", response_model=list[MonsterOut])
def list_monsters(
    q: str | None = None,
    facet1_num_gte: float | None = None,
    facet1_num_lte: float | None = None,
    facet1_text: str | None = None,
    facet2_text: str | None = None,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[MonsterOut]:
    rows = bestiary.list_monsters(
        session, ctx.campaign_id, q=q, facet1_num_gte=facet1_num_gte,
        facet1_num_lte=facet1_num_lte, facet1_text=facet1_text, facet2_text=facet2_text,
    )
    return [MonsterOut.model_validate(r) for r in rows]


@monsters_router.post("/import", response_model=ImportResult)
def import_bestiary(
    system_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ImportResult:
    if not registry.has_system(system_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule system not installed")
    return ImportResult(
        imported=bestiary.import_content_packs(session, ctx.campaign_id, system_id)
    )


# Static paths declared before /{monster_id} so they are not captured as an id.
@monsters_router.get("/export")
def export_bestiary(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> dict[str, Any]:
    return bestiary.export_monsters(session, ctx.campaign_id)


@monsters_router.post("/import-json")
def import_bestiary_json(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> dict[str, Any]:
    campaign = session.get(Campaign, ctx.campaign_id)
    system_id = campaign.rule_system_id if campaign else "dnd5e"
    return bestiary.import_monsters_json(session, ctx.campaign_id, system_id, payload)


@monsters_router.get("/{monster_id}", response_model=MonsterOut)
def get_monster(
    monster_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> MonsterOut:
    try:
        return MonsterOut.model_validate(
            bestiary.get_monster(session, ctx.campaign_id, monster_id)
        )
    except bestiary.MonsterNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "monster not found") from exc


@monsters_router.post("/{monster_id}/variant", response_model=MonsterOut, status_code=201)
def create_variant(
    monster_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> MonsterOut:
    try:
        return MonsterOut.model_validate(
            bestiary.make_variant(session, ctx.campaign_id, monster_id)
        )
    except bestiary.MonsterNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "monster not found") from exc
