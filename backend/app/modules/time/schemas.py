from __future__ import annotations

from pydantic import BaseModel, Field


class ClockFormatted(BaseModel):
    label: str
    weekday: str
    month: str
    day: int
    year: int
    time: str
    season: str | None
    seconds: int


class ClockOut(BaseModel):
    time_game: int  # seconds since the calendar epoch
    calendar_name: str
    calendar: dict[str, object]  # the full definition, so clients can format any time
    realtime_enabled: bool
    realtime_paused: bool  # paused while a combat is running (6s/round takes over)
    formatted: ClockFormatted


class AdvanceRequest(BaseModel):
    days: int = Field(default=0, ge=0)
    hours: int = Field(default=0, ge=0)
    minutes: int = Field(default=0, ge=0)
    seconds: int = Field(default=0, ge=0)
    reason: str = "manual"


class RealtimeRequest(BaseModel):
    enabled: bool


class SetClockRequest(BaseModel):
    time_game: int  # absolute seconds since the calendar epoch
    set_as_start: bool = True  # also record this as the campaign's start time
    reason: str = "clock set"


class FiredEvent(BaseModel):
    #: NULL in a preview when the occurrence has not been compiled into the queue yet.
    scheduled_event_id: str | None
    title: str
    at_time: int
    at_label: str
    narrative: str


class AdvanceReport(BaseModel):
    from_time: int
    to_time: int
    reason: str
    formatted: ClockFormatted
    fired: list[FiredEvent] = []


class AdvancePreview(BaseModel):
    from_time: int
    to_time: int
    would_fire: list[FiredEvent] = []


class ScheduledEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    fire_at_game: int
    action_type: str = Field(pattern="^(narrate|set_flag)$")
    action_json: dict[str, object] = {}
    recurrence_days: int | None = Field(default=None, ge=1)


class ScheduledEventOut(BaseModel):
    id: str
    title: str
    fire_at_game: int
    fire_at_label: str
    action_type: str
    recurrence_days: int | None
    status: str
