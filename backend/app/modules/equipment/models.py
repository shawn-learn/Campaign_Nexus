from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LibraryEntry(Base):
    """A campaign-independent equipment *template* in the shared library.

    The library is a global catalogue GMs draw from (like the bestiary's shared
    content): a template is not tied to any campaign and is never held or located.
    Importing one into a campaign materialises a normal entity-backed ``Equipment``
    definition (which the campaign then owns and can customise). ``source`` marks
    where the template came from — ``"srd"`` for seeded content, ``"custom"`` for
    GM-authored entries.
    """

    __tablename__ = "equipment_library"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(String, nullable=False, default="mundane", index=True)
    rarity: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    requires_attunement: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    value_gp: Mapped[str | None] = mapped_column(String, nullable=True)
    weight_lb: Mapped[float | None] = mapped_column(Float, nullable=True)
    properties: Mapped[str | None] = mapped_column(Text, nullable=True)
    attunement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "srd" for seeded content, "custom" for GM-authored library entries.
    source: Mapped[str] = mapped_column(String, nullable=False, default="custom", index=True)


class Equipment(Base):
    """Catalog definition for a type of item — described once, wiki-backed.

    One ``Equipment`` row answers "what *is* this thing?" — its game properties,
    rarity, and GM notes.  Individual physical copies are tracked by ``Item``.

    Backed by an ``Entity`` of type ``"equipment"`` so it gets search, the link
    graph, article pages, and tag support for free.
    """

    __tablename__ = "equipment"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Provenance: the library template this definition was imported from, if any.
    # Lets the UI show "already imported" and avoid duplicate imports.
    library_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("equipment_library.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # "magical" | "mundane"
    item_type: Mapped[str] = mapped_column(String, nullable=False, default="mundane", index=True)
    # "common" | "uncommon" | "rare" | "very_rare" | "legendary" | None
    rarity: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    requires_attunement: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    # Reference value per copy, e.g. "5 gp"
    value_gp: Mapped[str | None] = mapped_column(String, nullable=True)
    weight_lb: Mapped[float | None] = mapped_column(Float, nullable=True)
    # GM notes: damage dice, stat bonuses, special abilities, etc.
    properties: Mapped[str | None] = mapped_column(Text, nullable=True)
    attunement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Item(Base):
    """A specific physical copy of an ``Equipment`` definition in the world.

    One ``Equipment`` definition can have many ``Item`` copies.  Each copy is
    independently located and owned — e.g. five shovels defined once but placed
    at five different locations.

    ``current_holder_type``, ``current_holder_id``, and ``current_location_id``
    are **projections** of the ``item_transferred`` event log — never written
    directly by callers, only by ``projectors.py``.

    ``instance_label`` is an optional GM-supplied distinguisher for a specific
    copy, e.g. "the rusty one" or "Grandpa's Shovel".
    """

    __tablename__ = "item"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    equipment_id: Mapped[str] = mapped_column(
        String, ForeignKey("equipment.entity_id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Optional label that distinguishes this copy from others of the same type
    instance_label: Mapped[str | None] = mapped_column(String, nullable=True)
    # GM notes specific to this copy (e.g. its current condition)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Projections — maintained by projectors.py
    # "party" | "pc" | "npc" | "location" | "unowned"
    current_holder_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Entity id of PC / NPC / location; NULL for party or unowned
    current_holder_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Where the copy physically resides (separate from *who* carries it)
    current_location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )


class ItemOwnershipHistory(Base):
    """Full provenance timeline for one ``Item`` copy — a projection of
    ``item_transferred`` events.

    Half-open intervals: ``to_game IS NULL`` means "still held here".
    """

    __tablename__ = "item_ownership_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # FK to the *instance*, not the equipment definition
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("item.id", ondelete="CASCADE"), index=True, nullable=False
    )
    holder_type: Mapped[str | None] = mapped_column(String, nullable=True)
    holder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    from_game: Mapped[int] = mapped_column(Integer, nullable=False)
    to_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause_event_id: Mapped[str] = mapped_column(String, nullable=False)

