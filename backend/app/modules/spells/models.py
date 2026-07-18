from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Spell(Base):
    """A campaign-independent spell reference entry in the shared catalog.

    Keyed logically by ``(name, source)`` — a spell can appear in more than one book.
    Booleans are stored as ``Integer`` to match the rest of the schema (see
    ``equipment.LibraryEntry.requires_attunement``).
    """

    __tablename__ = "spell"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    school: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    casting_time: Mapped[str | None] = mapped_column(String, nullable=True)
    range_text: Mapped[str | None] = mapped_column(String, nullable=True)
    component_v: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    component_s: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    component_m: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    concentration: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    ritual: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    # Comma-separated class names (Wizard, Sorcerer, …); indexed via LIKE, not exact.
    classes: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    higher_levels: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_types: Mapped[str | None] = mapped_column(String, nullable=True)
    saving_throw: Mapped[str | None] = mapped_column(String, nullable=True)
