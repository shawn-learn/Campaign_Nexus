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
from app.modules.npcs.models import Npc
from app.modules.playbook.models import Encounter, PartyMember
from app.modules.playbook.schemas import (
    CombatantSpec,
    DifficultyOut,
    EncounterCombatantOut,
    EncounterOut,
    EnvironmentSpec,
)
from app.modules.rules import registry
from app.modules.rules.models import Monster, StatBlock
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity, Link
from app.modules.wiki.schemas import EntityCreate

LOCATED_AT = "located_at"


class EncounterNotFound(LookupError):
    pass


def _monster_doc(
    session: Session,
    monster_id: str,
    *,
    campaign_id: str | None = None,
    monster_name: str | None = None,
) -> tuple[str, dict[str, Any], str] | None:
    """Resolve a combatant to ``(name, doc, resolved_by)``.

    ``monster_id`` is not a foreign key, so a bestiary re-import can leave it dangling. When
    it misses, fall back to the recorded ``monster_name`` within the campaign rather than
    dropping the creature — a stale ID should degrade, not erase the combatant.
    """
    monster = session.get(Monster, monster_id)
    resolved_by = "id"
    if monster is None and monster_name and campaign_id:
        monster = session.scalars(
            select(Monster)
            .where(Monster.campaign_id == campaign_id, Monster.name == monster_name)
            .limit(1)
        ).first()
        resolved_by = "name"
    if monster is None:
        return None
    block = session.get(StatBlock, monster.stat_block_id)
    return monster.name, (json.loads(block.doc_json) if block else {}), resolved_by


def _npc_doc(
    session: Session,
    npc_id: str,
    *,
    campaign_id: str | None = None,
    npc_name: str | None = None,
) -> tuple[str, dict[str, Any], bool, str] | None:
    """Resolve an NPC combatant to ``(name, doc, has_stats, resolved_by)``.

    Same staleness fallback as ``_monster_doc``. ``has_stats`` is False when the NPC has no
    stat block attached: they belong to the scene, but there is nothing to fight with — the
    roster still shows them, and combat simply doesn't seed them.
    """
    npc = session.get(Npc, npc_id)
    resolved_by = "id"
    if (npc is None or npc.campaign_id != campaign_id) and npc_name and campaign_id:
        npc = session.scalars(
            select(Npc)
            .join(Entity, Entity.id == Npc.entity_id)
            .where(Npc.campaign_id == campaign_id, Entity.name == npc_name)
            .limit(1)
        ).first()
        resolved_by = "name"
    if npc is None:
        return None
    entity = session.get(Entity, npc.entity_id)
    name = entity.name if entity else "(unnamed)"
    block = session.get(StatBlock, npc.stat_block_id) if npc.stat_block_id else None
    if block is None:
        return name, {}, False, resolved_by
    return name, json.loads(block.doc_json), True, resolved_by


def _party_docs(session: Session, campaign_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(StatBlock.doc_json)
        .join(PartyMember, PartyMember.stat_block_id == StatBlock.id)
        .where(PartyMember.active, StatBlock.campaign_id == campaign_id)
    )
    return [json.loads(d) for d in rows]


def _resolve(
    session: Session, spec: dict[str, Any], campaign_id: str | None
) -> tuple[str, dict[str, Any], bool, str] | None:
    """One roster line → ``(name, doc, has_stats, resolved_by)``, monster or NPC."""
    if spec.get("npc_id"):
        return _npc_doc(
            session, spec["npc_id"],
            campaign_id=campaign_id, npc_name=spec.get("npc_name"),
        )
    resolved = _monster_doc(
        session, spec["monster_id"],
        campaign_id=campaign_id, monster_name=spec.get("monster_name"),
    )
    return None if resolved is None else (resolved[0], resolved[1], True, resolved[2])


def _combatants_out(
    session: Session, specs: list[dict[str, Any]], campaign_id: str | None = None
) -> list[EncounterCombatantOut]:
    out: list[EncounterCombatantOut] = []
    for spec in specs:
        resolved = _resolve(session, spec, campaign_id)
        out.append(
            EncounterCombatantOut(
                monster_id=spec.get("monster_id"),
                npc_id=spec.get("npc_id"),
                name=resolved[0] if resolved else "(missing)",
                count=int(spec.get("count", 1)), side=spec.get("side", "foe"),
                resolved_by=resolved[3] if resolved else None,
                has_stats=resolved[2] if resolved else False,
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
        resolved = _resolve(session, spec, campaign.id)
        # A statless NPC prices at nothing, so it would only add a zero — and asking the
        # plugin to rate an empty document is asking it to guess.
        if resolved and resolved[2]:
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
        combatants=_combatants_out(session, specs, campaign.id),
        environment=[EnvironmentSpec.model_validate(e) for e in json.loads(encounter.environment_json)],
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
    environment: list[EnvironmentSpec] | None = None,
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
        environment_json=json.dumps([e.model_dump() for e in (environment or [])]),
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
    rows = session.scalars(
        select(Encounter)
        .where(Encounter.campaign_id == campaign.id)
        # Hide encounters whose entity has been soft-deleted. Deleting a wiki entity only
        # stamps `deleted_at_real`, so the Encounter row survives and — without this — kept
        # showing up in the list and the combat page's "start an encounter" picker, where a
        # deleted encounter looks exactly like a live one with no monsters in it.
        .join(Entity, Entity.id == Encounter.entity_id)
        .where(Entity.deleted_at_real.is_(None))
    )
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
    environment: list[EnvironmentSpec] | None = None,
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
    if environment is not None:
        encounter.environment_json = json.dumps([e.model_dump() for e in environment])
    session.commit()
    return to_out(session, campaign, encounter)
