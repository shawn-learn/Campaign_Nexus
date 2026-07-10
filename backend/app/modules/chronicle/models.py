from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Session(Base):
    """One real-world game session (docs/04, §6.4).

    Kept as a standalone Chronicle table (not an entity) so this context stays
    independent of the wiki. At most one session per campaign is 'live' at a time
    (enforced in the service); while live, the pipeline stamps its id onto every event.
    """

    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("campaign_id", "session_number", name="uq_session_campaign_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_number: Mapped[int] = mapped_column(Integer, nullable=False)
    real_date: Mapped[str | None] = mapped_column(String, nullable=True)
    # planned | live | completed
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    clock_start_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_end_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class TimelineEntry(Base):
    """Curated projection of significant events + manual lore (docs/04, §6.4).

    ``event_id`` is NULL for manual entries (GM-authored lore, possibly pre-campaign →
    negative ``occurred_at_game``). Projected entries are rebuildable from the event log.
    """

    __tablename__ = "timeline_entry"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("domain_event.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at_game: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    significance: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_hidden: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)


class TimelineEntity(Base):
    """Timeline entry <-> entity, for filtering the timeline by entity."""

    __tablename__ = "timeline_entity"

    timeline_id: Mapped[str] = mapped_column(
        String, ForeignKey("timeline_entry.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
