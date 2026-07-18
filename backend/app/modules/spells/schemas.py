from __future__ import annotations

from pydantic import BaseModel, Field

SCHOOLS = (
    "Abjuration", "Conjuration", "Divination", "Enchantment",
    "Evocation", "Illusion", "Necromancy", "Transmutation",
)


class SpellOut(BaseModel):
    id: str
    name: str
    source: str
    level: int
    school: str | None
    casting_time: str | None
    range_text: str | None
    component_v: bool
    component_s: bool
    component_m: bool
    material: str | None
    concentration: bool
    ritual: bool
    classes: str | None
    duration: str | None
    description: str | None
    higher_levels: str | None
    damage_types: str | None
    saving_throw: str | None


class SpellFacetsOut(BaseModel):
    """Filter options actually present in the catalog, so the UI need not fetch every row."""

    sources: list[str]
    classes: list[str]


class SpellCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source: str = ""
    level: int = Field(ge=0, le=9)
    school: str | None = None
    casting_time: str | None = None
    range_text: str | None = None
    component_v: bool = False
    component_s: bool = False
    component_m: bool = False
    material: str | None = None
    concentration: bool = False
    ritual: bool = False
    classes: str | None = None
    duration: str | None = None
    description: str | None = None
    higher_levels: str | None = None
    damage_types: str | None = None
    saving_throw: str | None = None
