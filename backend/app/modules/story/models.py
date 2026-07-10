from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StoryNode(Base):
    """A potential/actual narrative beat — an extension of a 'story_node' wiki entity.

    Lifecycle (FR-4.4): ``possible → active → resolved | abandoned``, resolved manually by
    the GM in MVP. ``consequences_json`` is an ordered, validated action list run when the
    node is activated. Position is graph layout the React Flow editor persists.
    """

    __tablename__ = "story_node"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="possible")
    pos_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pos_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: [{"action": "set_flag"|"activate_quest"|..., ...params}] — a closed catalog (§14.4).
    consequences_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class StoryEdge(Base):
    """A directed transition between beats, gated by an optional condition predicate.

    Branching = several edges out of a node; merging = several into one. ``condition_expr``
    is the DSL source, parsed and validated on save (never stored as executable code)."""

    __tablename__ = "story_edge"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_node: Mapped[str] = mapped_column(
        String, ForeignKey("story_node.entity_id", ondelete="CASCADE"), nullable=False
    )
    to_node: Mapped[str] = mapped_column(
        String, ForeignKey("story_node.entity_id", ondelete="CASCADE"), nullable=False
    )
    condition_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
