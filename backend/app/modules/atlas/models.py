from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Media(Base):
    """An uploaded binary (map image / handout), content-addressed on disk (docs/05 §7.9)."""

    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)  # map_image|image|handout
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime: Mapped[str] = mapped_column(String, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)  # relative to media_dir
    created_at_real: Mapped[str] = mapped_column(String, nullable=False)


class Map(Base):
    """Image-backed extension of a 'map' entity. Leaflet renders the image with CRS.Simple,
    so pixel coordinates *are* the coordinate system (no tiling required for MVP sizes)."""

    __tablename__ = "map"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    media_id: Mapped[str] = mapped_column(String, ForeignKey("media.id"), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    parent_map_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="SET NULL"), nullable=True
    )
    map_kind: Mapped[str] = mapped_column(String, nullable=False, default="region")


class MapMarker(Base):
    """A pin at pixel (x, y) that peeks a target entity and/or drills into a child map."""

    __tablename__ = "map_marker"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    map_id: Mapped[str] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="CASCADE"), index=True, nullable=False
    )
    x: Mapped[float] = mapped_column(Float, nullable=False)  # pixel coords in source image space
    y: Mapped[float] = mapped_column(Float, nullable=False)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    child_map_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str] = mapped_column(String, nullable=False, default="default")


class MapRegion(Base):
    """A closed polygon in image-pixel space — a province, a district, a zone of effect.

    Same target semantics as a marker (peek an entity and/or drill into a child map); it
    just has an area instead of a point.
    """

    __tablename__ = "map_region"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    map_id: Mapped[str] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    polygon_json: Mapped[str] = mapped_column(Text, nullable=False)  # [[x, y], ...]
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    child_map_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str] = mapped_column(String, nullable=False, default="default")
