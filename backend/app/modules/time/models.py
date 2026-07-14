from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ScheduledEvent(Base):
    """A future occurrence the time engine fires when the clock passes it (docs/07, §9.6)."""

    __tablename__ = "scheduled_event"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    fire_at_game: Mapped[int] = mapped_column(Integer, nullable=False)
    recurrence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = one-shot
    action_type: Mapped[str] = mapped_column(String, nullable=False)  # narrate | set_flag
    action_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    title: Mapped[str] = mapped_column(String, nullable=False)
    created_by_kind: Mapped[str] = mapped_column(String, nullable=False, default="gm")
    source_entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | fired | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
