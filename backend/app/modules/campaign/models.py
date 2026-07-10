from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)


class RuleSystem(Base):
    __tablename__ = "rule_system"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # 'dnd5e', 'nimble'
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)


class Campaign(Base):
    __tablename__ = "campaign"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_system_id: Mapped[str] = mapped_column(
        String, ForeignKey("rule_system.id"), nullable=False
    )
    calendar_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    clock_time_game: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # seconds
    campaign_start_game: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_session_id: Mapped[str | None] = mapped_column(String, nullable=True)  # live session
    # Real-time ticking: while enabled (and not paused for combat), the clock advances with
    # wall-clock time, anchored at ``realtime_anchor_real`` (docs/07, §9.4).
    realtime_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    realtime_anchor_real: Mapped[str | None] = mapped_column(String, nullable=True)
    realtime_paused: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)
    archived_at_real: Mapped[str | None] = mapped_column(String, nullable=True)


class CampaignMember(Base):
    __tablename__ = "campaign_member"

    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # owner|editor|viewer


class CampaignFlag(Base):
    """Named campaign-state variable (docs/04, §6.7). Lives in the campaign context (the
    shared bottom layer) so the time and story engines can both read/write it. Written
    only inside a command transaction that also emits ``flag_changed``."""

    __tablename__ = "campaign_flag"

    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="null")
    updated_at_game: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
