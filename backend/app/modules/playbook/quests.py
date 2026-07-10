"""Quests: a status machine over a wiki entity, a deadline, and a dependency DAG (FR-10).

Three ideas do the work here:

1. **The quest *is* an entity.** Its prose, tags, mentions and backlinks are the wiki's job;
   this module owns only the structured half (type, status, giver, rewards, objectives).
2. **Status is event-derived.** Every transition runs through ``command_tx`` and emits a
   ``quest_*`` domain event, so the timeline narrates the quest without a second write path.
   The ``quest.status`` column is a projection you are allowed to read (docs/06, §8.3).
3. **Deadlines are scheduled events.** Setting one registers a ``quest_status`` scheduled
   event at that time (``created_by_kind='quest_deadline'``); when the clock passes it, the
   handler registered below expires the quest *inside the advance transaction* — so the
   clock move, the expiry, and its timeline entry commit together (FR-10.3).

Dependencies are acyclic ``depends_on`` links in the knowledge graph, not columns: quest A
``depends_on`` quest B means B must be finished first, and the graph view draws B → A.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pipeline import CommandContext, command_tx
from app.modules.campaign.models import Campaign
from app.modules.playbook.models import Quest
from app.modules.playbook.schemas import (
    Objective,
    QuestBrief,
    QuestCreate,
    QuestEdge,
    QuestGraph,
    QuestNode,
    QuestOut,
    QuestUpdate,
)
from app.modules.time import scheduled
from app.modules.time import service as time_service
from app.modules.time.calendar import CalendarMath
from app.modules.time.models import ScheduledEvent
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity, Link
from app.modules.wiki.schemas import EntityCreate

QUEST_TYPES = ("main", "side", "hidden")

#: The lifecycle (FR-10.1). Terminal states have no outgoing edges.
STATUSES = ("unknown", "available", "active", "completed", "failed", "expired", "abandoned")
_TRANSITIONS: dict[str, frozenset[str]] = {
    "unknown": frozenset({"available", "active", "abandoned"}),
    "available": frozenset({"active", "failed", "expired", "abandoned"}),
    "active": frozenset({"completed", "failed", "expired", "abandoned"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "expired": frozenset(),
    "abandoned": frozenset({"active"}),  # a dropped thread can be picked back up
}
#: Statuses at which a deadline still bites. Reaching any other status disarms it.
LIVE_STATUSES = frozenset({"unknown", "available", "active"})

#: status -> (event_type, narrative verb)
_STATUS_EVENTS: dict[str, tuple[str, str]] = {
    "available": ("quest_revealed", "is now available"),
    "active": ("quest_accepted", "was accepted"),
    "completed": ("quest_completed", "was completed"),
    "failed": ("quest_failed", "was failed"),
    "expired": ("quest_expired", "expired"),
    "abandoned": ("quest_abandoned", "was abandoned"),
    "unknown": ("quest_status_changed", "is unknown again"),
}

DEPENDS_ON = "depends_on"
DEADLINE_ACTION = "quest_status"


class QuestError(ValueError):
    pass


class QuestNotFound(LookupError):
    pass


class InvalidTransition(QuestError):
    pass


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def ensure_quest_rows(session: Session, campaign_id: str) -> None:
    """Give every 'quest' entity its extension row (status 'unknown'), idempotently.

    A quest can be born in the wiki — ``POST /entities {entity_type: 'quest'}``, an @mention
    create-in-place, an import — and those routes know nothing about this module. Rather than
    make the entity registry aware of quests, the quest reads heal the gap on the way past,
    the same way ``ensure_builtin_link_types`` seeds the link vocabulary.
    """
    missing = session.scalars(
        select(Entity.id).where(
            Entity.campaign_id == campaign_id,
            Entity.entity_type == "quest",
            Entity.deleted_at_real.is_(None),
            Entity.id.not_in(select(Quest.entity_id).where(Quest.campaign_id == campaign_id)),
        )
    ).all()
    if not missing:
        return
    for entity_id in missing:
        session.add(Quest(entity_id=entity_id, campaign_id=campaign_id))
    session.commit()


def _require(session: Session, campaign_id: str, quest_id: str) -> Quest:
    quest = session.get(Quest, quest_id)
    if quest is None:
        ensure_quest_rows(session, campaign_id)
        quest = session.get(Quest, quest_id)
    if quest is None or quest.campaign_id != campaign_id:
        raise QuestNotFound(quest_id)
    return quest


def _entity(session: Session, quest: Quest) -> Entity:
    entity = session.get(Entity, quest.entity_id)
    if entity is None:  # pragma: no cover - FK guarantees this
        raise QuestNotFound(quest.entity_id)
    return entity


def _objectives(quest: Quest) -> list[Objective]:
    try:
        raw = json.loads(quest.objectives_json)
    except json.JSONDecodeError:  # pragma: no cover - written by us
        return []
    return [
        Objective(text=str(o.get("text", "")), done=bool(o.get("done")))
        for o in raw
        if isinstance(o, dict)
    ]


def _dependency_ids(session: Session, quest_id: str) -> tuple[list[str], list[str]]:
    """(``depends_on`` targets, quests unlocked by this one)."""
    depends_on = list(
        session.scalars(
            select(Link.to_entity).where(
                Link.from_entity == quest_id, Link.link_type_id == DEPENDS_ON
            )
        )
    )
    unlocks = list(
        session.scalars(
            select(Link.from_entity).where(
                Link.to_entity == quest_id, Link.link_type_id == DEPENDS_ON
            )
        )
    )
    return depends_on, unlocks


def _blocked_by(session: Session, campaign_id: str, depends_on: list[str]) -> list[str]:
    """Prerequisite quests that are not yet completed — the quest is blocked while non-empty."""
    if not depends_on:
        return []
    rows = session.scalars(
        select(Quest).where(Quest.campaign_id == campaign_id, Quest.entity_id.in_(depends_on))
    )
    return [q.entity_id for q in rows if q.status != "completed"]


def _out(session: Session, cal: CalendarMath, now_game: int, quest: Quest) -> QuestOut:
    entity = _entity(session, quest)
    giver_name = None
    if quest.giver_npc_id:
        giver = session.get(Entity, quest.giver_npc_id)
        giver_name = giver.name if giver is not None else None
    depends_on, unlocks = _dependency_ids(session, quest.entity_id)
    try:
        rewards = json.loads(quest.rewards_json)
    except json.JSONDecodeError:  # pragma: no cover
        rewards = {}
    return QuestOut(
        entity_id=quest.entity_id,
        name=entity.name,
        summary=entity.summary,
        quest_type=quest.quest_type,
        status=quest.status,
        giver_npc_id=quest.giver_npc_id,
        giver_name=giver_name,
        rewards=rewards,
        deadline_game=quest.deadline_game,
        deadline_label=cal.format(quest.deadline_game)["label"] if quest.deadline_game else None,
        overdue=_is_overdue(quest, now_game),
        objectives=_objectives(quest),
        depends_on=depends_on,
        unlocks=unlocks,
        blocked_by=_blocked_by(session, quest.campaign_id, depends_on),
    )


def _is_overdue(quest: Quest, now_game: int) -> bool:
    return (
        quest.deadline_game is not None
        and quest.status in LIVE_STATUSES
        and now_game > quest.deadline_game
    )


def list_quests(
    session: Session, campaign: Campaign, *, status: str | None = None
) -> list[QuestOut]:
    ensure_quest_rows(session, campaign.id)
    cal = time_service.calendar_for(campaign)
    stmt = select(Quest).where(Quest.campaign_id == campaign.id)
    if status:
        stmt = stmt.where(Quest.status == status)
    quests = list(session.scalars(stmt))
    quests.sort(key=lambda q: (STATUSES.index(q.status), q.deadline_game or 1 << 62))
    return [_out(session, cal, campaign.clock_time_game, q) for q in quests]


def get_quest(session: Session, campaign: Campaign, quest_id: str) -> QuestOut:
    quest = _require(session, campaign.id, quest_id)
    cal = time_service.calendar_for(campaign)
    return _out(session, cal, campaign.clock_time_game, quest)


def active_quest_briefs(session: Session, campaign: Campaign) -> list[QuestBrief]:
    """The dashboard's quest panel: everything not in a terminal state (FR-7.3/FR-14.1)."""
    ensure_quest_rows(session, campaign.id)
    cal = time_service.calendar_for(campaign)
    now = campaign.clock_time_game
    rows = session.scalars(
        select(Quest).where(
            Quest.campaign_id == campaign.id, Quest.status.in_(sorted(LIVE_STATUSES))
        )
    )
    briefs = [
        QuestBrief(
            id=q.entity_id,
            name=_entity(session, q).name,
            entity_type="quest",
            summary=_entity(session, q).summary,
            status=q.status,
            quest_type=q.quest_type,
            deadline_game=q.deadline_game,
            deadline_label=cal.format(q.deadline_game)["label"] if q.deadline_game else None,
            overdue=_is_overdue(q, now),
        )
        for q in rows
    ]
    briefs.sort(key=lambda b: (b.deadline_game is None, b.deadline_game or 0, b.name))
    return briefs


# --------------------------------------------------------------------------- #
# Graph (FR-10.4) — nodes + edges for the React Flow view; dagre lays it out client-side
# --------------------------------------------------------------------------- #
def graph(session: Session, campaign: Campaign) -> QuestGraph:
    ensure_quest_rows(session, campaign.id)
    quests = {q.entity_id: q for q in session.scalars(
        select(Quest).where(Quest.campaign_id == campaign.id)
    )}
    now = campaign.clock_time_game
    nodes = [
        QuestNode(
            id=q.entity_id,
            name=_entity(session, q).name,
            status=q.status,
            quest_type=q.quest_type,
            overdue=_is_overdue(q, now),
        )
        for q in quests.values()
    ]
    edges: list[QuestEdge] = []
    for link in session.scalars(
        select(Link).where(Link.campaign_id == campaign.id, Link.link_type_id == DEPENDS_ON)
    ):
        # Edge direction is *prerequisite → dependent*: the graph reads left-to-right in
        # play order, which is the reverse of how the link is stored.
        if link.from_entity in quests and link.to_entity in quests:
            edges.append(QuestEdge(id=link.id, source=link.to_entity, target=link.from_entity))
    return QuestGraph(nodes=nodes, edges=edges)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def create_quest(
    session: Session, campaign: Campaign, data: QuestCreate, *, created_by: str
) -> QuestOut:
    if data.quest_type not in QUEST_TYPES:
        raise QuestError(f"unknown quest_type: {data.quest_type}")
    if data.status not in STATUSES:
        raise QuestError(f"unknown status: {data.status}")

    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="quest", name=data.name, summary=data.summary),
        created_by=created_by,
    )
    quest = Quest(
        entity_id=entity.id, campaign_id=campaign.id, quest_type=data.quest_type,
        status=data.status, giver_npc_id=data.giver_npc_id,
        rewards_json=json.dumps(data.rewards),
        objectives_json=json.dumps([o.model_dump() for o in data.objectives]),
    )
    session.add(quest)
    session.commit()

    if data.deadline_game is not None:
        set_deadline(session, campaign, entity.id, data.deadline_game)
    if data.giver_npc_id:
        wiki_service.create_link(
            session, campaign.id, entity.id,
            to_entity=data.giver_npc_id, link_type_id="given_by",
        )
    return get_quest(session, campaign, entity.id)


def update_quest(
    session: Session, campaign: Campaign, quest_id: str, data: QuestUpdate
) -> QuestOut:
    quest = _require(session, campaign.id, quest_id)
    fields = data.model_dump(exclude_unset=True)

    if "quest_type" in fields and fields["quest_type"] is not None:
        if fields["quest_type"] not in QUEST_TYPES:
            raise QuestError(f"unknown quest_type: {fields['quest_type']}")
        quest.quest_type = fields["quest_type"]
    if "giver_npc_id" in fields:
        quest.giver_npc_id = fields["giver_npc_id"] or None
    if "rewards" in fields and fields["rewards"] is not None:
        quest.rewards_json = json.dumps(fields["rewards"])
    if "objectives" in fields and fields["objectives"] is not None:
        quest.objectives_json = json.dumps([dict(o) for o in fields["objectives"]])
    session.commit()

    if "deadline_game" in fields:
        set_deadline(session, campaign, quest_id, fields["deadline_game"])
    return get_quest(session, campaign, quest_id)


def _emit_status(
    ctx: CommandContext, quest: Quest, name: str, to_status: str, *, at_time: int | None = None
) -> None:
    event_type, verb = _STATUS_EVENTS[to_status]
    ctx.emit(
        event_type,
        payload={"quest_id": quest.entity_id, "status": to_status, "quest_type": quest.quest_type},
        narrative=f"Quest '{name}' {verb}.",
        occurred_at_game=at_time,
        subject_entity_ids=(quest.entity_id,),
    )


def set_status(
    session: Session, campaign: Campaign, quest_id: str, to_status: str, *, actor: str = "gm"
) -> QuestOut:
    quest = _require(session, campaign.id, quest_id)
    if to_status not in STATUSES:
        raise QuestError(f"unknown status: {to_status}")
    if to_status == quest.status:
        return get_quest(session, campaign, quest_id)
    if to_status not in _TRANSITIONS[quest.status]:
        raise InvalidTransition(f"cannot go from '{quest.status}' to '{to_status}'")

    name = _entity(session, quest).name
    with command_tx(session, campaign.id, actor=actor) as ctx:
        quest.status = to_status
        if to_status not in LIVE_STATUSES:
            # The deadline can no longer bite; retract its scheduled event.
            scheduled.cancel_pending_for_source(
                session, campaign.id, quest.entity_id, DEADLINE_ACTION
            )
        _emit_status(ctx, quest, name, to_status)
    return get_quest(session, campaign, quest_id)


def set_deadline(
    session: Session, campaign: Campaign, quest_id: str, deadline_game: int | None
) -> QuestOut:
    """Arm, move, or clear a quest's deadline. The scheduled event mirrors the column."""
    quest = _require(session, campaign.id, quest_id)
    quest.deadline_game = deadline_game
    if deadline_game is None:
        scheduled.cancel_pending_for_source(
            session, campaign.id, quest.entity_id, DEADLINE_ACTION
        )
    else:
        name = _entity(session, quest).name
        scheduled.schedule_for_source(
            session, campaign.id,
            source_entity_id=quest.entity_id,
            action_type=DEADLINE_ACTION,
            action={"quest_id": quest.entity_id, "status": "expired"},
            fire_at_game=deadline_game,
            title=f"Deadline: {name}",
            created_by_kind="quest_deadline",
        )
    session.commit()
    return get_quest(session, campaign, quest_id)


def toggle_objective(
    session: Session, campaign: Campaign, quest_id: str, index: int, done: bool
) -> QuestOut:
    quest = _require(session, campaign.id, quest_id)
    objectives = [o.model_dump() for o in _objectives(quest)]
    if not 0 <= index < len(objectives):
        raise QuestError(f"no objective at index {index}")
    if objectives[index]["done"] == done:
        return get_quest(session, campaign, quest_id)

    objectives[index]["done"] = done
    name = _entity(session, quest).name
    with command_tx(session, campaign.id, actor="gm") as ctx:
        quest.objectives_json = json.dumps(objectives)
        if done:
            ctx.emit(
                "quest_objective_done",
                payload={"quest_id": quest.entity_id, "index": index},
                narrative=f"'{name}': {objectives[index]['text']}",
                subject_entity_ids=(quest.entity_id,),
            )
    return get_quest(session, campaign, quest_id)


def add_dependency(
    session: Session, campaign: Campaign, quest_id: str, depends_on_id: str
) -> QuestOut:
    """``quest_id`` depends on ``depends_on_id``. Cycles are rejected by the wiki (acyclic type)."""
    _require(session, campaign.id, quest_id)
    _require(session, campaign.id, depends_on_id)
    wiki_service.create_link(
        session, campaign.id, quest_id, to_entity=depends_on_id, link_type_id=DEPENDS_ON
    )
    return get_quest(session, campaign, quest_id)


def remove_dependency(
    session: Session, campaign: Campaign, quest_id: str, depends_on_id: str
) -> QuestOut:
    link = session.scalar(
        select(Link).where(
            Link.campaign_id == campaign.id,
            Link.from_entity == quest_id,
            Link.to_entity == depends_on_id,
            Link.link_type_id == DEPENDS_ON,
        )
    )
    if link is None:
        raise QuestNotFound(f"{quest_id} does not depend on {depends_on_id}")
    wiki_service.delete_link(session, campaign.id, link.id)
    return get_quest(session, campaign, quest_id)


# --------------------------------------------------------------------------- #
# Deadline firing — registered with the time engine's action registry
# --------------------------------------------------------------------------- #
def _deadline_execute(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    """Runs inside ``advance_time``'s transaction — no commits, no new command_tx."""
    quest = session.get(Quest, str(action.get("quest_id", "")))
    to_status = str(action.get("status", "expired"))
    if quest is None or quest.campaign_id != campaign_id:
        return f"{event.title}: quest no longer exists."

    name = _entity(session, quest).name
    if quest.status not in LIVE_STATUSES:
        # Resolved before the deadline landed — nothing to expire, and nothing to narrate.
        return f"Deadline for '{name}' passed, but it was already {quest.status}."

    quest.status = to_status
    session.flush()
    _emit_status(ctx, quest, name, to_status, at_time=at_time)
    return f"Quest '{name}' {_STATUS_EVENTS[to_status][1]}."


def _deadline_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return f"{event.title} — quest would be {action.get('status', 'expired')}."


scheduled.register_action(
    DEADLINE_ACTION, execute=_deadline_execute, describe=_deadline_describe
)
