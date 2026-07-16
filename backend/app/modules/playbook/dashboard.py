"""Live session dashboard — the composite read that powers the run-the-table view (FR-14).

This sits in the playbook (top orchestration) layer because it stitches together every
sibling context in one read transaction (ADR-006): the clock (time), party + encounters +
combat (playbook), the knowledge graph — quests, NPCs-here, encounters-here (wiki), and the
live session + notes + recent events (chronicle). ~8 indexed queries, one round trip.

Two small bits of *UI state* live in ``campaign.settings_json`` and are written directly
(no domain event), mirroring how the realtime toggle is a settings mutation: the GM's
``current_location_id`` (drives NPCs-here / encounters-here) and the list of
``pinned_entity_ids`` shown on the dashboard.
"""

from __future__ import annotations

import json

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.domain_event import DomainEvent
from app.modules.campaign.models import Campaign
from app.modules.chronicle.models import Session as GameSession
from app.modules.playbook import combat, quests
from app.modules.playbook import service as party_service
from app.modules.playbook.models import CombatRun
from app.modules.playbook.schemas import (
    CombatRunOut,
    DashboardOut,
    DashboardSession,
    EntityBrief,
    EventBrief,
    QuestBrief,
)
from app.modules.time import service as time_service
from app.modules.wiki.models import Entity, Link

_RECENT_EVENTS = 12
_RECENT_NOTES = 8


class DashboardError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Settings-backed UI state (current location + pins)
# --------------------------------------------------------------------------- #
def _settings(campaign: Campaign) -> dict[str, object]:
    raw = json.loads(campaign.settings_json or "{}")
    return raw if isinstance(raw, dict) else {}

def _pinned_ids(campaign: Campaign) -> list[str]:
    ids = _settings(campaign).get("pinned_entity_ids")
    return [str(x) for x in ids] if isinstance(ids, list) else []

def _current_location_id(campaign: Campaign) -> str | None:
    loc = _settings(campaign).get("current_location_id")
    return str(loc) if isinstance(loc, str) else None

def _require_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.campaign_id != campaign_id or entity.deleted_at_real:
        raise DashboardError("entity not found")
    return entity

def set_current_location(
    session: Session, campaign: Campaign, entity_id: str | None
) -> None:
    if entity_id is not None:
        _require_entity(session, campaign.id, entity_id)
    settings = _settings(campaign)
    if entity_id is None:
        settings.pop("current_location_id", None)
    else:
        settings["current_location_id"] = entity_id
    campaign.settings_json = json.dumps(settings)
    session.commit()

def set_pin(session: Session, campaign: Campaign, entity_id: str, pinned: bool) -> None:
    if pinned:
        _require_entity(session, campaign.id, entity_id)
    settings = _settings(campaign)
    ids = _pinned_ids(campaign)
    if pinned and entity_id not in ids:
        ids.append(entity_id)
    elif not pinned:
        ids = [x for x in ids if x != entity_id]
    settings["pinned_entity_ids"] = ids
    campaign.settings_json = json.dumps(settings)
    session.commit()


# --------------------------------------------------------------------------- #
# Composite read
# --------------------------------------------------------------------------- #
def _brief(entity: Entity) -> EntityBrief:
    return EntityBrief(
        id=entity.id, name=entity.name, entity_type=entity.entity_type, summary=entity.summary
    )

def _located_at(
    session: Session, campaign_id: str, location_id: str, entity_type: str
) -> list[Entity]:
    """Live entities of ``entity_type`` currently ``located_at`` the given location."""
    stmt = (
        select(Entity)
        .join(Link, Link.from_entity == Entity.id)
        .where(
            Link.campaign_id == campaign_id,
            Link.link_type_id == "located_at",
            Link.to_entity == location_id,
            Entity.entity_type == entity_type,
            Entity.deleted_at_real.is_(None),
        )
        .order_by(Entity.name)
    )
    return list(session.scalars(stmt))

def _event_brief(event: DomainEvent) -> EventBrief:
    return EventBrief(
        id=event.id,
        event_type=event.event_type,
        narrative=event.narrative_text,
        occurred_at_game=event.occurred_at_game,
        recorded_at_real=event.recorded_at_real,
    )

def _recent_events(session: Session, campaign_id: str) -> list[EventBrief]:
    stmt = (
        select(DomainEvent)
        .where(DomainEvent.campaign_id == campaign_id)
        .order_by(desc(DomainEvent.seq))
        .limit(_RECENT_EVENTS)
    )
    return [_event_brief(e) for e in session.scalars(stmt)]

def _recent_notes(session: Session, campaign_id: str) -> list[EventBrief]:
    stmt = (
        select(DomainEvent)
        .where(
            DomainEvent.campaign_id == campaign_id,
            DomainEvent.event_type == "note_captured",
        )
        .order_by(desc(DomainEvent.seq))
        .limit(_RECENT_NOTES)
    )
    return [_event_brief(e) for e in session.scalars(stmt)]

def _active_combat(session: Session, campaign_id: str) -> CombatRunOut | None:
    stmt = (
        select(CombatRun)
        # A run still rolling initiative hasn't begun, but it is very much in play — the
        # dashboard should surface it rather than let it vanish until someone hits Begin.
        .where(CombatRun.campaign_id == campaign_id, CombatRun.status.in_(("setup", "active")))
        .order_by(desc(CombatRun.started_at_game))
        .limit(1)
    )
    run = session.scalars(stmt).first()
    if run is None:
        return None
    total = combat._total_actions(session, run.id)
    return CombatRunOut(
        run_id=run.id, encounter_id=run.encounter_id, status=run.status,
        cursor=run.fold_cursor, total_actions=total,
        can_undo=run.fold_cursor > 0, can_redo=run.fold_cursor < total,
        state=combat.state_of(session, run),
        initiative_dice=combat.initiative_die(session, run),
    )

def _live_session(session: Session, campaign: Campaign) -> DashboardSession | None:
    if campaign.current_session_id is None:
        return None
    gs = session.get(GameSession, campaign.current_session_id)
    if gs is None:
        return None
    return DashboardSession(id=gs.id, session_number=gs.session_number, status=gs.status)

def _active_quests(session: Session, campaign: Campaign) -> list[QuestBrief]:
    """Delegated to the quest module: 'active' is a status machine, not an entity_type."""
    return quests.active_quest_briefs(session, campaign)

def _pinned(session: Session, campaign: Campaign) -> list[EntityBrief]:
    briefs: list[EntityBrief] = []
    for eid in _pinned_ids(campaign):
        entity = session.get(Entity, eid)
        if entity is not None and entity.campaign_id == campaign.id and not entity.deleted_at_real:
            briefs.append(_brief(entity))
    return briefs

def build(session: Session, campaign: Campaign) -> DashboardOut:
    """Assemble the full dashboard payload in one read transaction (docs/10 §13.5)."""
    clock = time_service.read_clock(session, campaign)
    party = party_service.to_out(
        session, party_service.get_or_create_party(session, campaign.id)
    )

    location_id = _current_location_id(campaign)
    current_location: EntityBrief | None = None
    npcs_here: list[EntityBrief] = []
    encounters_here: list[EntityBrief] = []
    if location_id is not None:
        loc = session.get(Entity, location_id)
        if loc is not None and loc.campaign_id == campaign.id and not loc.deleted_at_real:
            current_location = _brief(loc)
            npcs_here = [_brief(e) for e in _located_at(session, campaign.id, location_id, "npc")]
            encounters_here = [
                _brief(e) for e in _located_at(session, campaign.id, location_id, "encounter")
            ]

    return DashboardOut(
        clock=clock,
        session=_live_session(session, campaign),
        party=party,
        active_quests=_active_quests(session, campaign),
        current_location=current_location,
        npcs_here=npcs_here,
        encounters_here=encounters_here,
        pinned=_pinned(session, campaign),
        recent_events=_recent_events(session, campaign.id),
        notes=_recent_notes(session, campaign.id),
        active_combat=_active_combat(session, campaign.id),
    )
