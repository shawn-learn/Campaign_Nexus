"""Encounter builder (docs/04, §6.6). An encounter is a wiki entity (so it links into the
knowledge graph) plus structured combat data; difficulty is estimated by the rules plugin
against the current party.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.campaign.models import Campaign
from app.modules.playbook.models import Encounter, PartyMember
from app.modules.playbook.schemas import (
    CombatantSpec,
    DifficultyOut,
    EncounterCombatantOut,
    EncounterOut,
)
from app.modules.rules import registry
from app.modules.rules.models import Monster, StatBlock
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity, Link
from app.modules.wiki.schemas import EntityCreate

LOCATED_AT = "located_at"


class EncounterNotFound(LookupError):
    pass


def _monster_doc(session: Session, monster_id: str) -> tuple[str, dict[str, Any]] | None:
    monster = session.get(Monster, monster_id)
    if monster is None:
        return None
    block = session.get(StatBlock, monster.stat_block_id)
    return monster.name, (json.loads(block.doc_json) if block else {})


def _party_docs(session: Session, campaign_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(StatBlock.doc_json)
        .join(PartyMember, PartyMember.stat_block_id == StatBlock.id)
        .where(PartyMember.active, StatBlock.campaign_id == campaign_id)
    )
    return [json.loads(d) for d in rows]


def _combatants_out(
    session: Session, specs: list[dict[str, Any]]
) -> list[EncounterCombatantOut]:
    out: list[EncounterCombatantOut] = []
    for spec in specs:
        resolved = _monster_doc(session, spec["monster_id"])
        name = resolved[0] if resolved else "(missing)"
        out.append(
            EncounterCombatantOut(
                monster_id=spec["monster_id"], name=name,
                count=int(spec.get("count", 1)), side=spec.get("side", "foe"),
            )
        )
    return out


def _difficulty(
    session: Session, campaign: Campaign, specs: list[dict[str, Any]]
) -> DifficultyOut:
    system = registry.get_system(campaign.rule_system_id)
    party = _party_docs(session, campaign.id)
    foes: list[tuple[dict[str, Any], int]] = []
    for spec in specs:
        if spec.get("side", "foe") != "foe":
            continue
        resolved = _monster_doc(session, spec["monster_id"])
        if resolved:
            foes.append((resolved[1], int(spec.get("count", 1))))
    report = system.encounter_difficulty(party, foes)
    return DifficultyOut(**report)


def _location_id(session: Session, encounter_id: str) -> str | None:
    return session.scalar(
        select(Link.to_entity).where(
            Link.from_entity == encounter_id, Link.link_type_id == LOCATED_AT
        )
    )


def to_out(session: Session, campaign: Campaign, encounter: Encounter) -> EncounterOut:
    specs = json.loads(encounter.combatants_json)
    entity = session.get(Entity, encounter.entity_id)
    return EncounterOut(
        id=encounter.entity_id,
        name=entity.name if entity else "",
        terrain=encounter.terrain,
        hazards=encounter.hazards,
        tactics=encounter.tactics,
        combatants=_combatants_out(session, specs),
        difficulty=_difficulty(session, campaign, specs),
        location_id=_location_id(session, encounter.entity_id),
    )


def create_encounter(
    session: Session,
    campaign: Campaign,
    *,
    name: str,
    terrain: str | None,
    hazards: str | None,
    tactics: str | None,
    combatants: list[CombatantSpec],
    location_id: str | None,
    created_by: str,
) -> EncounterOut:
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="encounter", name=name), created_by=created_by,
    )
    encounter = Encounter(
        entity_id=entity.id,
        campaign_id=campaign.id,
        terrain=terrain,
        hazards=hazards,
        tactics=tactics,
        combatants_json=json.dumps([c.model_dump() for c in combatants]),
    )
    session.add(encounter)
    session.commit()

    if location_id:
        wiki_service.create_link(
            session, campaign.id, entity.id, to_entity=location_id, link_type_id=LOCATED_AT
        )
    return to_out(session, campaign, encounter)


def _require(session: Session, campaign_id: str, encounter_id: str) -> Encounter:
    encounter = session.get(Encounter, encounter_id)
    if encounter is None or encounter.campaign_id != campaign_id:
        raise EncounterNotFound(encounter_id)
    return encounter


def get_encounter(session: Session, campaign: Campaign, encounter_id: str) -> EncounterOut:
    return to_out(session, campaign, _require(session, campaign.id, encounter_id))


def list_encounters(session: Session, campaign: Campaign) -> list[EncounterOut]:
    rows = session.scalars(select(Encounter).where(Encounter.campaign_id == campaign.id))
    return [to_out(session, campaign, e) for e in rows]


def update_encounter(
    session: Session,
    campaign: Campaign,
    encounter_id: str,
    *,
    terrain: str | None,
    hazards: str | None,
    tactics: str | None,
    combatants: list[CombatantSpec] | None,
) -> EncounterOut:
    encounter = _require(session, campaign.id, encounter_id)
    if terrain is not None:
        encounter.terrain = terrain
    if hazards is not None:
        encounter.hazards = hazards
    if tactics is not None:
        encounter.tactics = tactics
    if combatants is not None:
        encounter.combatants_json = json.dumps([c.model_dump() for c in combatants])
    session.commit()
    return to_out(session, campaign, encounter)
