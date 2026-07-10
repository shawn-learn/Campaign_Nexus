from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StoryNodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    status: str = "possible"
    pos_x: float = 0.0
    pos_y: float = 0.0
    consequences: list[dict[str, Any]] = []


class StoryNodeUpdate(BaseModel):
    pos_x: float | None = None
    pos_y: float | None = None
    consequences: list[dict[str, Any]] | None = None


class StoryNodeOut(BaseModel):
    entity_id: str
    name: str
    summary: str | None
    status: str
    pos_x: float
    pos_y: float
    consequences: list[dict[str, Any]]


class StoryEdgeIn(BaseModel):
    from_node: str
    to_node: str
    condition_expr: str | None = None
    label: str | None = None


class StoryEdgeOut(BaseModel):
    id: str
    from_node: str
    to_node: str
    condition_expr: str | None
    label: str | None


class StoryGraphOut(BaseModel):
    nodes: list[StoryNodeOut]
    edges: list[StoryEdgeOut]
    flags: dict[str, Any]


class StoryStatusIn(BaseModel):
    status: str


class NodeStatusResult(BaseModel):
    node: StoryNodeOut
    #: One line per consequence that ran when the node was activated.
    applied: list[str]


class Suggestion(BaseModel):
    node_id: str
    name: str
    via_node_id: str
    via_node_name: str
    edge_label: str | None
    condition_expr: str | None


class ConditionCheckIn(BaseModel):
    expr: str


class ConditionCheck(BaseModel):
    valid: bool
    error: str | None
    #: The truth value against current campaign state (``None`` if it didn't parse).
    result: bool | None


class SetFlagIn(BaseModel):
    key: str = Field(min_length=1)
    value: Any = True
