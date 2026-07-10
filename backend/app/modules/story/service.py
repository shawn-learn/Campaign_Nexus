"""Story engine service: nodes, edges, condition evaluation, and on-demand suggestions.

The GM authors a directed graph of beats. Edges carry conditions over campaign state. The
engine never fires a beat itself (FR-4.4): it *evaluates* the conditions leaving the beats
that have already happened and **suggests** which possible beat is now reachable, for the GM
to confirm. Confirming activates the node and runs its consequences.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign import flags as campaign_flags
from app.modules.campaign.models import Campaign
from app.modules.npcs.models import Npc
from app.modules.playbook.models import Quest
from app.modules.story import conditions, consequences
from app.modules.story.models import StoryEdge, StoryNode
from app.modules.story.schemas import (
    ConditionCheck,
    NodeStatusResult,
    StoryEdgeIn,
    StoryEdgeOut,
    StoryGraphOut,
    StoryNodeIn,
    StoryNodeOut,
    StoryNodeUpdate,
    Suggestion,
)
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate

STATUSES = ("possible", "active", "resolved", "abandoned")
#: Beats that have "happened" — their outgoing edges are what the engine evaluates.
REACHED = frozenset({"active", "resolved"})
_TRANSITIONS: dict[str, frozenset[str]] = {
    "possible": frozenset({"active", "abandoned"}),
    "active": frozenset({"resolved", "abandoned"}),
    "resolved": frozenset({"active"}),  # re-open a beat if the GM changes their mind
    "abandoned": frozenset({"possible"}),
}


class StoryError(ValueError):
    pass


class StoryNotFound(LookupError):
    pass


class InvalidTransition(StoryError):
    pass


# --------------------------------------------------------------------------- #
# Condition context — the only state the DSL can read
# --------------------------------------------------------------------------- #
class _Context:
    def __init__(self, session: Session, campaign_id: str) -> None:
        self._session = session
        self._cid = campaign_id
        self._flags = campaign_flags.list_flags(session, campaign_id)

    def flag(self, key: str) -> Any:
        return self._flags.get(key)

    def quest_status(self, quest_id: str) -> str | None:
        q = self._session.get(Quest, quest_id)
        return q.status if q is not None and q.campaign_id == self._cid else None

    def npc_status(self, npc_id: str) -> str | None:
        n = self._session.get(Npc, npc_id)
        return n.status if n is not None and n.campaign_id == self._cid else None

    def npc_location(self, npc_id: str) -> str | None:
        n = self._session.get(Npc, npc_id)
        return n.current_location_id if n is not None and n.campaign_id == self._cid else None


# --------------------------------------------------------------------------- #
# Reads / serialization
# --------------------------------------------------------------------------- #
def _require_node(session: Session, campaign_id: str, node_id: str) -> StoryNode:
    node = session.get(StoryNode, node_id)
    if node is None or node.campaign_id != campaign_id:
        raise StoryNotFound(node_id)
    return node


def _entity(session: Session, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None:  # pragma: no cover - FK guarantees this
        raise StoryNotFound(entity_id)
    return entity


def _node_out(session: Session, node: StoryNode) -> StoryNodeOut:
    entity = _entity(session, node.entity_id)
    return StoryNodeOut(
        entity_id=node.entity_id, name=entity.name, summary=entity.summary,
        status=node.status, pos_x=node.pos_x, pos_y=node.pos_y,
        consequences=json.loads(node.consequences_json),
    )


def _edge_out(edge: StoryEdge) -> StoryEdgeOut:
    return StoryEdgeOut(
        id=edge.id, from_node=edge.from_node, to_node=edge.to_node,
        condition_expr=edge.condition_expr, label=edge.label,
    )


def graph(session: Session, campaign: Campaign) -> StoryGraphOut:
    nodes = session.scalars(
        select(StoryNode).where(StoryNode.campaign_id == campaign.id)
    ).all()
    edges = session.scalars(
        select(StoryEdge).where(StoryEdge.campaign_id == campaign.id)
    ).all()
    return StoryGraphOut(
        nodes=[_node_out(session, n) for n in nodes],
        edges=[_edge_out(e) for e in edges],
        flags=campaign_flags.list_flags(session, campaign.id),
    )


def check_condition(session: Session, campaign: Campaign, expr: str) -> ConditionCheck:
    error = conditions.validate(expr)
    if error is not None:
        return ConditionCheck(valid=False, error=error, result=None)
    result = conditions.evaluate(expr, _Context(session, campaign.id))
    return ConditionCheck(valid=True, error=None, result=result)


# --------------------------------------------------------------------------- #
# Suggestions (FR-4.4) — the engine proposes, the GM disposes
# --------------------------------------------------------------------------- #
def suggestions(session: Session, campaign: Campaign) -> list[Suggestion]:
    """Possible beats reachable *now*: an edge from a reached beat whose condition holds."""
    ctx = _Context(session, campaign.id)
    nodes = {n.entity_id: n for n in session.scalars(
        select(StoryNode).where(StoryNode.campaign_id == campaign.id)
    )}
    out: list[Suggestion] = []
    seen: set[str] = set()
    for edge in session.scalars(
        select(StoryEdge).where(StoryEdge.campaign_id == campaign.id)
    ):
        source = nodes.get(edge.from_node)
        target = nodes.get(edge.to_node)
        if source is None or target is None:
            continue
        if source.status not in REACHED or target.status != "possible":
            continue
        if not conditions.evaluate(edge.condition_expr or "", ctx):
            continue
        if edge.to_node in seen:
            continue
        seen.add(edge.to_node)
        out.append(Suggestion(
            node_id=edge.to_node, name=_entity(session, edge.to_node).name,
            via_node_id=edge.from_node, via_node_name=_entity(session, edge.from_node).name,
            edge_label=edge.label, condition_expr=edge.condition_expr,
        ))
    return out


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def create_node(
    session: Session, campaign: Campaign, data: StoryNodeIn, *, created_by: str
) -> StoryNodeOut:
    if data.status not in STATUSES:
        raise StoryError(f"unknown status: {data.status}")
    cons = consequences.validate(data.consequences)
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="story_node", name=data.name, summary=data.summary),
        created_by=created_by,
    )
    node = StoryNode(
        entity_id=entity.id, campaign_id=campaign.id, status=data.status,
        pos_x=data.pos_x, pos_y=data.pos_y, consequences_json=json.dumps(cons),
    )
    session.add(node)
    session.commit()
    return _node_out(session, node)


def update_node(
    session: Session, campaign: Campaign, node_id: str, data: StoryNodeUpdate
) -> StoryNodeOut:
    node = _require_node(session, campaign.id, node_id)
    fields = data.model_dump(exclude_unset=True)
    if "pos_x" in fields and fields["pos_x"] is not None:
        node.pos_x = fields["pos_x"]
    if "pos_y" in fields and fields["pos_y"] is not None:
        node.pos_y = fields["pos_y"]
    if "consequences" in fields and fields["consequences"] is not None:
        node.consequences_json = json.dumps(consequences.validate(fields["consequences"]))
    session.commit()
    return _node_out(session, node)


def delete_node(session: Session, campaign: Campaign, node_id: str) -> None:
    node = _require_node(session, campaign.id, node_id)
    entity = session.get(Entity, node.entity_id)
    session.delete(node)  # edges cascade via FK
    if entity is not None:
        session.delete(entity)
    session.commit()


def set_node_status(
    session: Session, campaign: Campaign, node_id: str, to_status: str
) -> NodeStatusResult:
    """Move a beat's status. Activating it runs its consequences in order (FR-4.3)."""
    node = _require_node(session, campaign.id, node_id)
    if to_status not in STATUSES:
        raise StoryError(f"unknown status: {to_status}")
    if to_status == node.status:
        return NodeStatusResult(node=_node_out(session, node), applied=[])
    if to_status not in _TRANSITIONS[node.status]:
        raise InvalidTransition(f"cannot go from '{node.status}' to '{to_status}'")

    name = _entity(session, node.entity_id).name
    with command_tx(session, campaign.id, actor="gm") as ctx:
        node.status = to_status
        event = {
            "active": "story_node_activated", "resolved": "story_node_resolved",
            "abandoned": "story_node_abandoned", "possible": "story_node_reopened",
        }[to_status]
        ctx.emit(
            event, payload={"node_id": node.entity_id, "status": to_status},
            narrative=f"Story beat '{name}' {to_status}.",
            subject_entity_ids=(node.entity_id,),
        )

    # Consequences run *after* the status commit, each in its own command (they call other
    # services). Only activation triggers them.
    applied: list[str] = []
    if to_status == "active":
        session.refresh(campaign)
        applied = consequences.apply(
            session, campaign, json.loads(node.consequences_json)
        )
    return NodeStatusResult(node=_node_out(session, node), applied=applied)


# --------------------------------------------------------------------------- #
# Edges
# --------------------------------------------------------------------------- #
def create_edge(session: Session, campaign: Campaign, data: StoryEdgeIn) -> StoryEdgeOut:
    _require_node(session, campaign.id, data.from_node)
    _require_node(session, campaign.id, data.to_node)
    if data.from_node == data.to_node:
        raise StoryError("a story edge cannot loop a node to itself")
    error = conditions.validate(data.condition_expr or "")
    if error is not None:
        raise StoryError(f"invalid condition: {error}")
    edge = StoryEdge(
        id=new_id(), campaign_id=campaign.id, from_node=data.from_node, to_node=data.to_node,
        condition_expr=(data.condition_expr or None), label=data.label,
    )
    session.add(edge)
    session.commit()
    return _edge_out(edge)


def delete_edge(session: Session, campaign: Campaign, edge_id: str) -> None:
    edge = session.get(StoryEdge, edge_id)
    if edge is None or edge.campaign_id != campaign.id:
        raise StoryNotFound(edge_id)
    session.delete(edge)
    session.commit()


# --------------------------------------------------------------------------- #
# Flags (GM authoring convenience — sets world state the conditions read)
# --------------------------------------------------------------------------- #
def set_flag(session: Session, campaign: Campaign, key: str, value: Any) -> dict[str, Any]:
    with command_tx(session, campaign.id, actor="gm") as ctx:
        campaign_flags.set_flag(session, campaign.id, key, value, at_game=campaign.clock_time_game)
        ctx.emit(
            "flag_changed",
            payload={"key": key, "value": value, "source": "gm"},
            narrative=f"Flag '{key}' set to {json.dumps(value)}.",
        )
    return campaign_flags.list_flags(session, campaign.id)
