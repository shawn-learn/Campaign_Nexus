from __future__ import annotations

from pydantic import BaseModel, Field

NPC_STATUSES = ("alive", "dead", "missing", "unknown", "retired")


class NpcOut(BaseModel):
    entity_id: str
    name: str
    summary: str | None
    status: str
    current_location_id: str | None
    current_location_name: str | None
    has_met_party: bool
    last_party_interaction_game: int | None
    goals: str | None
    secrets: str | None
    voice_notes: str | None
    knows_about: list[str]
    #: The NPC's combat sheet, when one has been attached. Without it the NPC can still sit
    #: on an encounter's roster, but has no hit points to bring to a fight.
    stat_block_id: str | None = None
    stat_block_label: str | None = None
    #: True when the underlying wiki entity is soft-deleted (only listed with include_deleted).
    deleted: bool = False


class NpcCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    status: str = "alive"
    location_id: str | None = None
    goals: str | None = None
    secrets: str | None = None


class NpcUpdate(BaseModel):
    goals: str | None = None
    secrets: str | None = None
    voice_notes: str | None = None
    #: Attach (or, sent as null, detach) the NPC's combat sheet. Patched with
    #: ``exclude_unset``, so omitting it leaves the current link alone.
    stat_block_id: str | None = None


class RelocateIn(BaseModel):
    location_id: str | None = None
    reason: str | None = None


class StatusIn(BaseModel):
    status: str
    reason: str | None = None


class InteractionIn(BaseModel):
    summary: str | None = None


class HistoryRow(BaseModel):
    location_id: str | None
    location_name: str | None
    from_game: int
    from_label: str
    to_game: int | None
    to_label: str | None


class WhereOut(BaseModel):
    npc_id: str
    name: str
    #: Every place the NPC occupied across the queried window, in order.
    places: list[HistoryRow]
    at_game: int | None = None
    session_id: str | None = None


class ScheduleStop(BaseModel):
    at_seconds: int = Field(ge=0, description="second-of-day the NPC arrives")
    location_id: str


class ScheduleCreate(BaseModel):
    label: str = ""
    interval_days: int = Field(default=1, ge=1)
    stops: list[ScheduleStop] = Field(min_length=1)


class ScheduleOut(BaseModel):
    id: str
    npc_id: str
    label: str
    interval_days: int
    stops: list[ScheduleStop]
    active: bool
    materialized_through_game: int | None
