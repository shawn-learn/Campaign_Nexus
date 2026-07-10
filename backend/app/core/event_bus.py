"""In-process event bus (ADR-001/004).

Subscribers receive domain events *after commit*, so they never observe uncommitted
state. Anything correctness-critical belongs in the command handler's transaction
(synchronous projections), not here — bus subscribers are reactive conveniences
(dashboard cache invalidation, story-suggestion evaluation).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Subscriber = Callable[["EventRecord"], None]


@dataclass(frozen=True, slots=True)
class EventRecord:
    """The committed fact handed to bus subscribers."""

    id: str
    campaign_id: str
    seq: int
    event_type: str
    occurred_at_game: int
    recorded_at_real: str
    session_id: str | None
    actor: str
    payload: dict[str, object]
    narrative_text: str
    subject_entity_ids: tuple[str, ...] = ()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def publish(self, events: list[EventRecord]) -> None:
        for event in events:
            for subscriber in self._subscribers:
                subscriber(event)


# Process-wide singleton.
event_bus = EventBus()
