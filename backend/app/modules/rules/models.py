from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatBlock(Base):
    """A system-specific character sheet document (docs/05, §7.4).

    ``doc_json`` is authored data validated against the plugin's schema; ``derived_json`` is
    the plugin-computed cache, refreshed on every write. ``campaign_id`` NULL = shared
    content-pack block (Sprint 10+).
    """

    __tablename__ = "stat_block"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=True
    )
    rule_system_id: Mapped[str] = mapped_column(
        String, ForeignKey("rule_system.id"), nullable=False
    )
    sheet_type: Mapped[str] = mapped_column(String, nullable=False)  # pc | npc | monster
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    doc_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    derived_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class Monster(Base):
    """A bestiary entry: name + stat block + plugin-populated facet columns (docs/05, §7.3).

    ``source`` is ``content_pack:<id>@<ver>`` for imported SRD monsters or ``custom`` for
    GM-made ones; ``variant_of`` points at the original for copy-on-write variants.
    """

    __tablename__ = "monster"
    __table_args__ = (
        Index("ix_monster_facets", "campaign_id", "facet1_num", "facet1_text"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    stat_block_id: Mapped[str] = mapped_column(
        String, ForeignKey("stat_block.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False, default="custom")
    variant_of: Mapped[str | None] = mapped_column(
        String, ForeignKey("monster.id", ondelete="SET NULL"), nullable=True
    )
    facet1_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    facet2_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    facet1_text: Mapped[str | None] = mapped_column(String, nullable=True)
    facet2_text: Mapped[str | None] = mapped_column(String, nullable=True)
