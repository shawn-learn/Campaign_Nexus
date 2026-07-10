"""The append-only domain event log — backing store of the command pipeline.

Architectural note: the *table* lives in core because it is pipeline infrastructure
(ADR-004: no mutation without an event). The Chronicle *module* owns the higher-level
semantics built on top of it — the event-type catalog, projections, the timeline, and
sessions — and reads this model without core ever importing the module.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DomainEvent(Base):
    __tablename__ = "domain_event"
    __table_args__ = (UniqueConstraint("campaign_id", "seq", name="uq_event_campaign_seq"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, index=True, nullable=False)
    occurred_at_game: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at_real: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Entities this event is about (JSON list of ids) — powers timeline/session filtering
    # and session auto-linking without a separate join table.
    subject_entity_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
