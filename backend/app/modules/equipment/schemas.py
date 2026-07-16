from __future__ import annotations

from pydantic import BaseModel, Field

ITEM_TYPES = ("magical", "mundane")
RARITIES = ("common", "uncommon", "rare", "very_rare", "legendary")
HOLDER_TYPES = ("party", "pc", "npc", "location", "unowned")


# Equipment library (global, campaign-independent templates)

class LibraryEntryOut(BaseModel):
    id: str
    name: str
    summary: str | None
    item_type: str
    rarity: str | None
    requires_attunement: bool
    value_gp: str | None
    weight_lb: float | None
    properties: str | None
    attunement_notes: str | None
    source: str


class LibraryEntryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    item_type: str = "mundane"
    rarity: str | None = None
    requires_attunement: bool = False
    value_gp: str | None = None
    weight_lb: float | None = None
    properties: str | None = None
    attunement_notes: str | None = None


class LibraryEntryUpdate(BaseModel):
    name: str | None = None
    summary: str | None = None
    item_type: str | None = None
    rarity: str | None = None
    requires_attunement: bool | None = None
    value_gp: str | None = None
    weight_lb: float | None = None
    properties: str | None = None
    attunement_notes: str | None = None


class ImportFromLibrary(BaseModel):
    library_id: str


# Equipment (catalog definition)

class EquipmentOut(BaseModel):
    entity_id: str
    name: str
    summary: str | None
    item_type: str
    rarity: str | None
    requires_attunement: bool
    value_gp: str | None
    weight_lb: float | None
    properties: str | None
    attunement_notes: str | None
    instance_count: int
    #: The library template this definition was imported from, if any.
    library_id: str | None = None


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    item_type: str = "mundane"
    rarity: str | None = None
    requires_attunement: bool = False
    value_gp: str | None = None
    weight_lb: float | None = None
    properties: str | None = None
    attunement_notes: str | None = None


class EquipmentUpdate(BaseModel):
    properties: str | None = None
    attunement_notes: str | None = None
    value_gp: str | None = None
    weight_lb: float | None = None
    rarity: str | None = None
    requires_attunement: bool | None = None


# Item (individual copy / instance)

class ItemInstanceOut(BaseModel):
    item_id: str
    equipment_id: str
    equipment_name: str
    item_type: str
    rarity: str | None
    requires_attunement: bool
    value_gp: str | None
    instance_label: str | None
    notes: str | None
    current_holder_type: str | None
    current_holder_id: str | None
    current_holder_name: str | None
    current_location_id: str | None
    current_location_name: str | None


class ItemInstanceCreate(BaseModel):
    equipment_id: str
    instance_label: str | None = None
    notes: str | None = None
    initial_holder_type: str | None = None
    initial_holder_id: str | None = None
    initial_location_id: str | None = None


class ItemInstanceUpdate(BaseModel):
    instance_label: str | None = None
    notes: str | None = None


# Shared

class TransferIn(BaseModel):
    holder_type: str | None = None
    holder_id: str | None = None
    location_id: str | None = None
    reason: str | None = None


class OwnershipRow(BaseModel):
    holder_type: str | None
    holder_id: str | None
    holder_name: str | None
    location_id: str | None
    location_name: str | None
    from_game: int
    from_label: str
    to_game: int | None
    to_label: str | None
