"""Party service, including plugin-driven rests (docs/07 §9.4, docs/08 §10.2).

A rest advances the campaign clock by the system's rest duration (firing any scheduled
events en route) and then applies the plugin's rest rules to each party member's live
status — orchestrating the time and rules engines.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.money import format_coins
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.playbook.models import LocationConnection, Party, PartyMember
from app.modules.playbook.schemas import (
    LocationConnectionCreate,
    LocationConnectionOut,
    PartyMemberOut,
    PartyOut,
    PartyPatch,
    RestResult,
)
from app.modules.rules import registry
from app.modules.rules.interface import RuleSystem
from app.modules.rules.models import StatBlock
from app.modules.time import service as time_service
from app.modules.wiki.models import Entity


class PlaybookError(ValueError):
    pass


def get_or_create_party(session: Session, campaign_id: str) -> Party:
    party = session.scalar(select(Party).where(Party.campaign_id == campaign_id))
    if party is None:
        party = Party(id=new_id(), campaign_id=campaign_id)
        session.add(party)
        session.commit()
    return party


def _members(session: Session, party_id: str) -> list[PartyMember]:
    return list(
        session.scalars(select(PartyMember).where(PartyMember.party_id == party_id))
    )


def _member_out(session: Session, system: RuleSystem, member: PartyMember) -> PartyMemberOut:
    """``status`` is plugin-shaped; ``hp``/``max_hp`` are the plugin's reading of it, so the
    UI can show a health bar without knowing which key this system stores HP under."""
    block = session.get(StatBlock, member.stat_block_id)
    doc: dict[str, Any] = json.loads(block.doc_json) if block else {}
    status = json.loads(member.status_json)
    profile = system.combat_profile(block.sheet_type if block else "pc", doc, status)
    return PartyMemberOut(
        stat_block_id=member.stat_block_id,
        name=member.name,
        status=status,
        hp=int(profile["hp"]),
        max_hp=int(profile["max_hp"]),
        active=bool(member.active),
    )


def to_out(session: Session, party: Party) -> PartyOut:
    location = (
        session.get(Entity, party.current_location_id) if party.current_location_id else None
    )
    campaign = session.get(Campaign, party.campaign_id)
    system = registry.get_system(campaign.rule_system_id) if campaign else None
    return PartyOut(
        id=party.id,
        current_location_id=party.current_location_id,
        current_location_name=location.name if location else None,
        current_map_id=party.current_map_id,
        current_x=party.current_x,
        current_y=party.current_y,
        wealth_cp=party.wealth_cp,
        gold=party.wealth_cp // 100,
        wealth_label=format_coins(party.wealth_cp),
        inventory=json.loads(party.inventory_json),
        reputation=json.loads(party.reputation_json),
        rest_types=system.rest_types() if system else [],
        members=(
            [_member_out(session, system, m) for m in _members(session, party.id)]
            if system
            else []
        ),
    )


def patch_party(session: Session, campaign_id: str, body: PartyPatch) -> Party:
    party = get_or_create_party(session, campaign_id)
    if body.wealth_cp is not None:
        party.wealth_cp = max(0, body.wealth_cp)
    elif body.gold is not None:
        party.wealth_cp = max(0, body.gold) * 100
    if body.location_set:
        party.current_location_id = body.current_location_id
        if body.current_location_id:
            from app.modules.playbook.travel import resolve_location_coordinates
            map_id, x, y = resolve_location_coordinates(session, body.current_location_id)
            if map_id is not None:
                party.current_map_id = map_id
                party.current_x = x
                party.current_y = y
            else:
                party.current_map_id = None
                party.current_x = None
                party.current_y = None
        else:
            party.current_map_id = None
            party.current_x = None
            party.current_y = None
    if body.coordinates_set:
        party.current_map_id = body.current_map_id
        party.current_x = body.current_x
        party.current_y = body.current_y
    session.commit()
    return party


def list_connections(session: Session, campaign_id: str) -> list[LocationConnectionOut]:
    rows = session.scalars(
        select(LocationConnection).where(LocationConnection.campaign_id == campaign_id)
    ).all()
    out = []
    for r in rows:
        from_loc = session.get(Entity, r.from_location_id)
        to_loc = session.get(Entity, r.to_location_id)
        out.append(LocationConnectionOut(
            from_location_id=r.from_location_id,
            from_location_name=from_loc.name if from_loc else None,
            to_location_id=r.to_location_id,
            to_location_name=to_loc.name if to_loc else None,
            distance=r.distance,
            terrain=r.terrain,
        ))
    return out


def upsert_connection(
    session: Session, campaign_id: str, body: LocationConnectionCreate
) -> LocationConnectionOut:
    from_loc = session.get(Entity, body.from_location_id)
    to_loc = session.get(Entity, body.to_location_id)
    if not from_loc or from_loc.campaign_id != campaign_id:
        raise PlaybookError("from_location not found")
    if not to_loc or to_loc.campaign_id != campaign_id:
        raise PlaybookError("to_location not found")

    for (f_id, t_id) in [(body.from_location_id, body.to_location_id), (body.to_location_id, body.from_location_id)]:
        conn = session.get(LocationConnection, {"campaign_id": campaign_id, "from_location_id": f_id, "to_location_id": t_id})
        if conn is None:
            conn = LocationConnection(
                campaign_id=campaign_id,
                from_location_id=f_id,
                to_location_id=t_id,
                distance=body.distance,
                terrain=body.terrain,
            )
            session.add(conn)
        else:
            conn.distance = body.distance
            conn.terrain = body.terrain
    session.commit()

    return LocationConnectionOut(
        from_location_id=body.from_location_id,
        from_location_name=from_loc.name,
        to_location_id=body.to_location_id,
        to_location_name=to_loc.name,
        distance=body.distance,
        terrain=body.terrain,
    )


def add_member(
    session: Session, campaign_id: str, stat_block_id: str, hit_points: int | None
) -> Party:
    party = get_or_create_party(session, campaign_id)
    block = session.get(StatBlock, stat_block_id)
    if block is None or block.campaign_id != campaign_id:
        raise PlaybookError("stat block not found in this campaign")
    if block.sheet_type not in ("pc", "npc"):
        raise PlaybookError("only pc/npc sheets can join the party")

    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise PlaybookError("campaign not found")
    system = registry.get_system(campaign.rule_system_id)
    # The plugin owns the shape of live play-state; we only persist it.
    status = system.initial_status(
        block.sheet_type, json.loads(block.doc_json), hit_points
    )
    existing = session.get(PartyMember, {"party_id": party.id, "stat_block_id": stat_block_id})
    if existing is None:
        session.add(
            PartyMember(
                party_id=party.id, stat_block_id=stat_block_id,
                name=block.label or "PC", status_json=json.dumps(status), active=True,
            )
        )
        session.commit()
    return party


def remove_member(session: Session, campaign_id: str, stat_block_id: str) -> Party:
    party = get_or_create_party(session, campaign_id)
    member = session.get(PartyMember, {"party_id": party.id, "stat_block_id": stat_block_id})
    if member is not None:
        session.delete(member)
        session.commit()
    return party


def rest(session: Session, campaign_id: str, rest_type: str) -> RestResult:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise PlaybookError("campaign not found")
    system = registry.get_system(campaign.rule_system_id)
    if rest_type not in system.rest_types():
        raise PlaybookError(f"{campaign.rule_system_id} has no '{rest_type}' rest")

    from_time = campaign.clock_time_game
    duration = system.rest_duration_seconds(rest_type)
    if duration > 0:
        # Advance the clock through the rest, firing any scheduled events (own transaction).
        time_service.advance_time(
            session, campaign, delta_seconds=duration, reason=f"{rest_type} rest"
        )

    party = get_or_create_party(session, campaign_id)
    members = [m for m in _members(session, party.id) if m.active]
    with command_tx(session, campaign_id, actor="gm") as ctx:
        for member in members:
            block = session.get(StatBlock, member.stat_block_id)
            doc: dict[str, Any] = json.loads(block.doc_json) if block else {}
            new_status = system.apply_rest(rest_type, json.loads(member.status_json), doc)
            member.status_json = json.dumps(new_status)
        ctx.emit(
            f"{rest_type}_rest_completed",
            payload={"members": len(members)},
            narrative=f"The party completed a {rest_type} rest.",
        )

    session.refresh(campaign)
    return RestResult(
        rest_type=rest_type,
        from_time=from_time,
        to_time=campaign.clock_time_game,
        members=[_member_out(session, system, m) for m in _members(session, party.id)],
    )
