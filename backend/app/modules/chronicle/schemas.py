from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TimelineEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str | None
    session_id: str | None
    occurred_at_game: int
    title: str
    body: str | None
    icon: str | None
    significance: int
    is_hidden: bool


class ManualEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    occurred_at_game: int
    icon: str | None = None
    significance: int = Field(default=2, ge=1, le=4)
    entity_ids: list[str] = []


class TimelineEntryPatch(BaseModel):
    is_hidden: bool


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_number: int
    real_date: str | None
    status: str
    clock_start_game: int | None
    clock_end_game: int | None
    summary: str | None


class SessionCreate(BaseModel):
    real_date: str | None = None
    summary: str | None = None


class SessionEntityRef(BaseModel):
    entity_id: str
    name: str
    entity_type: str


class SessionEvent(BaseModel):
    event_type: str
    occurred_at_game: int
    narrative_text: str


class SessionDetail(SessionOut):
    events: list[SessionEvent] = []
    entities: list[SessionEntityRef] = []  # auto-linked (subjects of the session's events)


class NoteCreate(BaseModel):
    text: str = Field(min_length=1)
    entity_ids: list[str] = []
