from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("campaign_id", "name", name="uq_tag_campaign_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str | None] = mapped_column(String, nullable=True)


class EntityTag(Base):
    __tablename__ = "entity_tag"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )


class LinkType(Base):
    """Typed-edge vocabulary. ``campaign_id IS NULL`` = built-in (e.g. 'mentions')."""

    __tablename__ = "link_type"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    inverse_label: Mapped[str] = mapped_column(String, nullable=False)
    is_semantic: Mapped[bool] = mapped_column(Integer, default=False, nullable=False)


class Link(Base):
    """A typed directed edge. Bidirectionality is a query property (ADR-003):
    backlinks = rows WHERE to_entity = :id. ``source`` distinguishes GM-asserted
    ('explicit') edges from those derived from @mentions ('mention')."""

    __tablename__ = "link"
    __table_args__ = (
        UniqueConstraint("from_entity", "to_entity", "link_type_id", "source", name="uq_link_edge"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_entity: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_entity: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    link_type_id: Mapped[str] = mapped_column(
        String, ForeignKey("link_type.id"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="explicit")
    valid_from_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_to_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)


class ArticleSnapshot(Base):
    """A lightweight version history for entity articles (FR-13.4).

    One row per saved edit that actually changed the prose. Cheap insurance against a bad
    edit: the GM can read or restore an earlier version. Not event-sourced — this is a
    convenience log of a text field, not a domain fact.
    """

    __tablename__ = "article_snapshot"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    article_json: Mapped[str] = mapped_column(Text, nullable=False)
    #: First ~140 chars of plain text, so a version list reads without parsing each doc.
    preview: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)


class Entity(Base):
    """The registry row every wiki-visible object shares (docs/04, §6.1)."""

    __tablename__ = "entity"
    __table_args__ = (UniqueConstraint("campaign_id", "slug", name="uq_entity_campaign_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)
    updated_at_real: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at_real: Mapped[str | None] = mapped_column(String, nullable=True)
