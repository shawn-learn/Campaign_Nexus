"""Timeline projector — turns significant domain events into timeline entries (§8.4).

Registered with the core projection registry, so it runs inside every command
transaction and is replayed by ``rebuild_projections``. Only curated, world-significant
event types produce entries; wiki audit noise (entity_created, link_added, …) is excluded
by omission (§8.3).
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.event_bus import EventRecord
from app.core.ids import new_id
from app.core.projections import register_projector, register_reset
from app.modules.chronicle.models import TimelineEntity, TimelineEntry

# event_type -> (significance 1..4, icon)
TIMELINE_EVENTS: dict[str, tuple[int, str]] = {
    "world_event": (3, "✦"),
    "flag_changed": (1, "⚑"),
    "session_started": (2, "▶"),
    "session_ended": (2, "⏹"),
    "note_captured": (1, "✎"),
    # Quests (FR-10) — the status machine narrates itself here.
    "quest_revealed": (1, "❓"),
    "quest_accepted": (2, "❗"),
    "quest_objective_done": (1, "☑"),
    "quest_completed": (3, "✔"),
    "quest_failed": (3, "✘"),
    "quest_expired": (3, "⌛"),
    "quest_abandoned": (2, "⊘"),
    # NPC dynamics (FR-6). A relocation is minor noise on its own, but it is what makes
    # "where was X during session 7" answerable from the timeline as well as the projection.
    "party_traveled": (2, "🧭"),
    "party_moved": (2, "⇢"),
    # Rests are how a session's downtime reads back as story — and a multi-day journey
    # inserts them on the GM's behalf, so they must leave a trace (FR-8.1, FR-7.2).
    # Their *names* belong to the rule system (5e: short/long; Nimble: field/safe), so the
    # catalog matches them by suffix below rather than enumerating a system's vocabulary.
    "npc_relocated": (1, "→"),
    "npc_status_changed": (2, "☠"),
    "npc_met_party": (2, "🤝"),
    "combat_ended": (3, "⚔"),
    "treasure_discovered": (2, "◆"),
    # Story engine (FR-4): activating/resolving a beat is a significant narrative move.
    "story_node_activated": (3, "◈"),
    "story_node_resolved": (2, "◇"),
}


#: Event types the catalog matches by suffix, because their prefix is a plugin's word.
_SUFFIX_EVENTS: tuple[tuple[str, tuple[int, str]], ...] = (
    ("_rest_completed", (1, "🌙")),
)


def _spec_for(event_type: str) -> tuple[int, str] | None:
    spec = TIMELINE_EVENTS.get(event_type)
    if spec is not None:
        return spec
    for suffix, suffix_spec in _SUFFIX_EVENTS:
        if event_type.endswith(suffix):
            return suffix_spec
    return None


def timeline_projector(session: Session, event: EventRecord) -> None:
    spec = _spec_for(event.event_type)
    if spec is None:
        return
    significance, icon = spec
    entry = TimelineEntry(
        id=new_id(),
        campaign_id=event.campaign_id,
        event_id=event.id,
        session_id=event.session_id,
        occurred_at_game=event.occurred_at_game,
        title=event.narrative_text,
        icon=icon,
        significance=significance,
    )
    session.add(entry)
    session.flush()
    for entity_id in event.subject_entity_ids:
        session.add(TimelineEntity(timeline_id=entry.id, entity_id=entity_id))


def reset_timeline(session: Session, campaign_id: str | None) -> None:
    """Drop projected (event-derived) entries before a replay; keep GM-authored lore."""
    stmt = select(TimelineEntry.id).where(TimelineEntry.event_id.is_not(None))
    if campaign_id:
        stmt = stmt.where(TimelineEntry.campaign_id == campaign_id)
    projected = list(session.scalars(stmt))
    if not projected:
        return
    session.execute(delete(TimelineEntity).where(TimelineEntity.timeline_id.in_(projected)))
    session.execute(delete(TimelineEntry).where(TimelineEntry.id.in_(projected)))


def register() -> None:
    register_projector(timeline_projector)
    register_reset(reset_timeline)


register()
