from __future__ import annotations

from pydantic import BaseModel, Field

MAP_KINDS = ("world", "region", "city", "dungeon", "building")


class MarkerOut(BaseModel):
    id: str
    x: float
    y: float
    icon: str | None
    color: str | None
    note: str | None
    layer: str
    target_entity_id: str | None
    target_name: str | None
    target_type: str | None
    child_map_id: str | None
    child_map_name: str | None


class RegionOut(BaseModel):
    id: str
    name: str | None
    polygon: list[tuple[float, float]]
    color: str | None
    note: str | None
    layer: str
    target_entity_id: str | None
    target_name: str | None
    target_type: str | None
    child_map_id: str | None
    child_map_name: str | None


class RegionCreate(BaseModel):
    name: str | None = None
    #: Closed polygon in image-pixel space; the ring is implicit (last point joins the first).
    polygon: list[tuple[float, float]] = Field(min_length=3)
    color: str | None = None
    note: str | None = None
    layer: str = "default"
    target_entity_id: str | None = None
    child_map_id: str | None = None


class RegionUpdate(BaseModel):
    name: str | None = None
    polygon: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    color: str | None = None
    note: str | None = None
    layer: str | None = None
    target_entity_id: str | None = None
    child_map_id: str | None = None


class MapSummary(BaseModel):
    entity_id: str
    name: str
    description: str | None
    map_kind: str
    width_px: int
    height_px: int
    location_id: str | None
    parent_map_id: str | None
    marker_count: int
    scale_pixels_per_unit: float | None = None
    scale_unit: str | None = "mile"


class MapDetail(BaseModel):
    entity_id: str
    name: str
    description: str | None
    map_kind: str
    width_px: int
    height_px: int
    media_id: str
    location_id: str | None
    parent_map_id: str | None
    parent_map_name: str | None
    markers: list[MarkerOut]
    regions: list[RegionOut]
    #: Every layer name in use on this map — the viewer's filter chips (FR-3.x).
    layers: list[str]
    scale_pixels_per_unit: float | None = None
    scale_unit: str | None = "mile"



class MarkerCreate(BaseModel):
    x: float
    y: float
    icon: str | None = None
    color: str | None = None
    note: str | None = None
    layer: str = "default"
    target_entity_id: str | None = None
    child_map_id: str | None = None


class MarkerUpdate(BaseModel):
    x: float | None = None
    y: float | None = None
    icon: str | None = None
    color: str | None = None
    note: str | None = None
    layer: str | None = None
    target_entity_id: str | None = None
    child_map_id: str | None = None


class MapUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    description_set: bool = Field(
        default=False, description="Set true to apply description (including clearing to null)."
    )
    map_kind: str | None = None
    location_id: str | None = None
    parent_map_id: str | None = None
    scale_pixels_per_unit: float | None = None
    scale_unit: str | None = None
    scale_set: bool = Field(
        default=False, description="Set true to apply scale (including clearing to null)."
    )


class AttachmentOut(BaseModel):
    id: str
    entity_id: str
    media_id: str
    filename: str
    mime: str
    caption: str | None
    sort_order: int
