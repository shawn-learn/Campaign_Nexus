from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Npc(Base):
    """Structured extension of an 'npc' wiki entity (docs/04, §6.2).

    ``current_location_id``, ``has_met_party`` and ``last_party_interaction_game`` are
    **projections** of the event log — never written by a caller, only by the projectors
    below. ``status``/``goals``/``secrets`` are GM-authored fields.
    """

    __tablename__ = "npc"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # alive | dead | missing | unknown | retired
    status: Mapped[str] = mapped_column(String, nullable=False, default="alive", index=True)
    current_location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), index=True, nullable=True
    )
    has_met_party: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    last_party_interaction_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    secrets: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    stat_block_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("stat_block.id", ondelete="SET NULL"), nullable=True
    )


class NpcLocationHistory(Base):
    """Where an NPC was, and when — a projection of ``npc_relocated`` (FR-6.2).

    Half-open intervals: ``to_game IS NULL`` means "still there". Answering "where was X at
    time T" is one indexed range probe (docs/05 §7.9).
    """

    __tablename__ = "npc_location_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    npc_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    from_game: Mapped[int] = mapped_column(Integer, nullable=False)
    to_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause_event_id: Mapped[str] = mapped_column(String, nullable=False)


class NpcSchedule(Base):
    """A recurring itinerary (FR-6.5). Compiled to scheduled events *lazily* (docs/07 §9.6):
    a daily route never enqueues 365 rows — only the occurrences inside the window the clock
    is about to cross. ``materialized_through_game`` is how far that compilation has run.
    """

    __tablename__ = "npc_schedule"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    npc_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    #: {"interval_days": 1, "stops": [{"at_seconds": 28800, "location_id": "..."}]}
    rule_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    materialized_through_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
