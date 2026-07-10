"""NPC projections (docs/06, §8.4): current location, location history, met-the-party.

These run inside the command transaction that emitted the event, so an NPC's cached
location can never contradict the ``npc_relocated`` log. Everything here is derived — a
replay through ``rebuild_projections`` must reproduce it exactly, which is why each
projector is written to be **idempotent under replay** (reset first, then fold forward).

The projector also maintains the NPC's ``located_at`` edge in the knowledge graph, so the
wiki, the dashboard's NPCs-here panel, and this table all agree about where someone is.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.event_bus import EventRecord
from app.core.ids import new_id
from app.core.projections import register_projector, register_reset
from app.modules.npcs.models import Npc, NpcLocationHistory
from app.modules.wiki.models import Link
from app.modules.wiki.service import ensure_builtin_link_types

LOCATED_AT = "located_at"


def _npc(session: Session, campaign_id: str, npc_id: str) -> Npc | None:
    npc = session.get(Npc, npc_id)
    return npc if npc is not None and npc.campaign_id == campaign_id else None


def _sync_located_at(
    session: Session, campaign_id: str, npc_id: str, location_id: str | None
) -> None:
    """The NPC has exactly one ``located_at`` edge; relocation moves it."""
    session.execute(
        delete(Link).where(Link.from_entity == npc_id, Link.link_type_id == LOCATED_AT)
    )
    if location_id is None:
        return
    ensure_builtin_link_types(session)  # the vocabulary is seeded lazily; we may be first
    session.add(
        Link(
            id=new_id(), campaign_id=campaign_id, from_entity=npc_id, to_entity=location_id,
            link_type_id=LOCATED_AT, source="explicit", created_at_real=now_real_iso(),
        )
    )


def _relocated(session: Session, event: EventRecord) -> None:
    npc_id = str(event.payload.get("npc_id", ""))
    npc = _npc(session, event.campaign_id, npc_id)
    if npc is None:
        return
    location_id = event.payload.get("to")
    location_id = str(location_id) if isinstance(location_id, str) else None

    # A relocation to where they already are is not a move: an itinerary that revisits the
    # same stop must not open a second interval (and a replay must not duplicate one).
    open_row = session.scalar(
        select(NpcLocationHistory).where(
            NpcLocationHistory.npc_id == npc_id, NpcLocationHistory.to_game.is_(None)
        )
    )
    if open_row is not None and open_row.location_id == location_id:
        return

    # Close the open interval, then open the new one at this instant.
    session.execute(
        update(NpcLocationHistory)
        .where(NpcLocationHistory.npc_id == npc_id, NpcLocationHistory.to_game.is_(None))
        .values(to_game=event.occurred_at_game)
    )
    session.add(
        NpcLocationHistory(
            id=new_id(), campaign_id=event.campaign_id, npc_id=npc_id,
            location_id=location_id, from_game=event.occurred_at_game, to_game=None,
            cause_event_id=event.id,
        )
    )
    npc.current_location_id = location_id
    _sync_located_at(session, event.campaign_id, npc_id, location_id)
    session.flush()


def _status_changed(session: Session, event: EventRecord) -> None:
    npc = _npc(session, event.campaign_id, str(event.payload.get("npc_id", "")))
    if npc is None:
        return
    npc.status = str(event.payload.get("to", npc.status))
    session.flush()


def _met_party(session: Session, event: EventRecord) -> None:
    npc = _npc(session, event.campaign_id, str(event.payload.get("npc_id", "")))
    if npc is None:
        return
    npc.has_met_party = True
    npc.last_party_interaction_game = event.occurred_at_game
    session.flush()


_HANDLERS = {
    "npc_relocated": _relocated,
    "npc_status_changed": _status_changed,
    "npc_met_party": _met_party,
    "npc_interaction": _met_party,  # any interaction implies (and refreshes) a meeting
}


def npc_projector(session: Session, event: EventRecord) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is not None:
        handler(session, event)


def reset_npc_projections(session: Session, campaign_id: str | None) -> None:
    """Wipe derived NPC state before a replay. GM-authored columns are left alone."""
    history = delete(NpcLocationHistory)
    npcs = update(Npc).values(
        current_location_id=None, has_met_party=False, last_party_interaction_game=None
    )
    if campaign_id:
        history = history.where(NpcLocationHistory.campaign_id == campaign_id)
        npcs = npcs.where(Npc.campaign_id == campaign_id)
    session.execute(history)
    session.execute(npcs)
    # `located_at` edges out of NPCs are derived too; the replay re-creates them.
    npc_ids = select(Npc.entity_id)
    if campaign_id:
        npc_ids = npc_ids.where(Npc.campaign_id == campaign_id)
    session.execute(
        delete(Link).where(Link.link_type_id == LOCATED_AT, Link.from_entity.in_(npc_ids))
    )


def register() -> None:
    register_projector(npc_projector)
    register_reset(reset_npc_projections)


register()
