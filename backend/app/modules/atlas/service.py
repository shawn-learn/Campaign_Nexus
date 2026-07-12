"""Atlas service: map upload + storage, marker CRUD, drill-down resolution.

Maps are reference data (like stat blocks): the image and its markers are edited directly,
not through the event log. Creating the *map entity* still goes through the wiki write path
(so it lands in the graph, search, and the entity_created audit), but marker edits commit
plainly — they carry no domain meaning worth projecting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.config import get_settings
from app.core.ids import new_id
from app.modules.atlas import imagesize
from app.modules.atlas.models import EntityMedia, Map, MapMarker, MapRegion, Media
from app.modules.atlas.schemas import (
    AttachmentOut,
    MapDetail,
    MapSummary,
    MarkerCreate,
    MarkerOut,
    MarkerUpdate,
    RegionCreate,
    RegionOut,
    RegionUpdate,
)
from app.modules.campaign.models import Campaign
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}


class AtlasError(ValueError):
    pass


class MapNotFound(AtlasError):
    pass


# --------------------------------------------------------------------------- #
# Media storage (content-addressed under media_dir/<campaign>/<sha256>.<ext>)
# --------------------------------------------------------------------------- #
def _media_root() -> Path:
    return Path(get_settings().media_dir)


def media_abspath(media: Media) -> Path:
    return _media_root() / media.storage_path


def store_media_bytes(
    session: Session,
    campaign_id: str,
    data: bytes,
    *,
    filename: str,
    kind: str = "map_image",
    media_id: str | None = None,
) -> Media:
    """Write bytes content-addressed under ``media_dir/<campaign>/<sha256>.<ext>`` and record
    the row. Idempotent on disk: identical bytes reuse the same file. Used by upload *and* by
    the campaign archive importer (docs/13 §7.9)."""
    mime, _w, _h = imagesize.sniff(data)
    digest = hashlib.sha256(data).hexdigest()
    rel = f"{campaign_id}/{digest}.{_EXT[mime]}"
    dest = _media_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    media = Media(
        id=media_id or new_id(), campaign_id=campaign_id, kind=kind, filename=filename,
        mime=mime, bytes=len(data), storage_path=rel, created_at_real=now_real_iso(),
    )
    session.add(media)
    session.flush()
    return media


# --------------------------------------------------------------------------- #
# Maps
# --------------------------------------------------------------------------- #
def upload_map(
    session: Session,
    campaign: Campaign,
    *,
    name: str,
    data: bytes,
    filename: str,
    map_kind: str,
    location_id: str | None,
    parent_map_id: str | None,
    created_by: str,
) -> MapDetail:
    _mime, width, height = imagesize.sniff(data)
    media = store_media_bytes(session, campaign.id, data, filename=filename)
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="map", name=name), created_by=created_by,
    )
    map_row = Map(
        entity_id=entity.id, campaign_id=campaign.id, media_id=media.id,
        width_px=width, height_px=height, location_id=location_id,
        parent_map_id=parent_map_id, map_kind=map_kind,
    )
    session.add(map_row)
    session.commit()
    return get_map(session, campaign.id, entity.id)


def _require_map(session: Session, campaign_id: str, map_id: str) -> Map:
    m = session.get(Map, map_id)
    if m is None or m.campaign_id != campaign_id:
        raise MapNotFound(map_id)
    return m


def list_maps(session: Session, campaign_id: str) -> list[MapSummary]:
    rows = session.scalars(
        select(Map).where(Map.campaign_id == campaign_id).order_by(Map.map_kind)
    ).all()
    summaries: list[MapSummary] = []
    for m in rows:
        entity = session.get(Entity, m.entity_id)
        if entity is None or entity.deleted_at_real:
            continue
        count = session.scalar(
            select(func.count()).select_from(MapMarker).where(MapMarker.map_id == m.entity_id)
        )
        summaries.append(MapSummary(
            entity_id=m.entity_id, name=entity.name, map_kind=m.map_kind,
            width_px=m.width_px, height_px=m.height_px, location_id=m.location_id,
            parent_map_id=m.parent_map_id, marker_count=count or 0,
        ))
    return summaries


def _marker_out(session: Session, marker: MapMarker) -> MarkerOut:
    target_name, target_type, child_map_name = _names_for_targets(
        session, marker.target_entity_id, marker.child_map_id
    )
    return MarkerOut(
        id=marker.id, x=marker.x, y=marker.y, icon=marker.icon, color=marker.color,
        note=marker.note, layer=marker.layer,
        target_entity_id=marker.target_entity_id, target_name=target_name,
        target_type=target_type, child_map_id=marker.child_map_id,
        child_map_name=child_map_name,
    )


def _names_for_targets(
    session: Session, target_entity_id: str | None, child_map_id: str | None
) -> tuple[str | None, str | None, str | None]:
    target_name = target_type = child_map_name = None
    if target_entity_id:
        ent = session.get(Entity, target_entity_id)
        if ent is not None and not ent.deleted_at_real:
            target_name, target_type = ent.name, ent.entity_type
    if child_map_id:
        child = session.get(Entity, child_map_id)
        if child is not None and not child.deleted_at_real:
            child_map_name = child.name
    return target_name, target_type, child_map_name


def _region_out(session: Session, region: MapRegion) -> RegionOut:
    target_name, target_type, child_map_name = _names_for_targets(
        session, region.target_entity_id, region.child_map_id
    )
    return RegionOut(
        id=region.id, name=region.name, polygon=json.loads(region.polygon_json),
        color=region.color, note=region.note, layer=region.layer,
        target_entity_id=region.target_entity_id, target_name=target_name,
        target_type=target_type, child_map_id=region.child_map_id,
        child_map_name=child_map_name,
    )


def get_map(session: Session, campaign_id: str, map_id: str) -> MapDetail:
    m = _require_map(session, campaign_id, map_id)
    entity = session.get(Entity, m.entity_id)
    if entity is None:
        raise MapNotFound(map_id)
    parent_name = None
    if m.parent_map_id:
        parent = session.get(Entity, m.parent_map_id)
        parent_name = parent.name if parent else None
    markers = session.scalars(
        select(MapMarker).where(MapMarker.map_id == m.entity_id)
    ).all()
    regions = session.scalars(
        select(MapRegion).where(MapRegion.map_id == m.entity_id)
    ).all()
    layers = sorted({mk.layer for mk in markers} | {rg.layer for rg in regions})
    return MapDetail(
        entity_id=m.entity_id, name=entity.name, map_kind=m.map_kind,
        width_px=m.width_px, height_px=m.height_px, media_id=m.media_id,
        location_id=m.location_id, parent_map_id=m.parent_map_id,
        parent_map_name=parent_name,
        markers=[_marker_out(session, mk) for mk in markers],
        regions=[_region_out(session, rg) for rg in regions],
        layers=layers,
    )


def media_for_map(session: Session, campaign_id: str, map_id: str) -> Media:
    m = _require_map(session, campaign_id, map_id)
    media = session.get(Media, m.media_id)
    if media is None:
        raise MapNotFound(map_id)
    return media


def update_map(
    session: Session, campaign_id: str, map_id: str, *,
    name: str | None, map_kind: str | None,
    location_id: str | None, parent_map_id: str | None,
) -> MapDetail:
    m = _require_map(session, campaign_id, map_id)
    if map_kind is not None:
        m.map_kind = map_kind
    if location_id is not None:
        m.location_id = location_id or None
    if parent_map_id is not None:
        m.parent_map_id = parent_map_id or None
    if name is not None:
        entity = session.get(Entity, m.entity_id)
        if entity is not None:
            entity.name = name
            entity.updated_at_real = now_real_iso()
    session.commit()
    return get_map(session, campaign_id, map_id)


def delete_map(session: Session, campaign_id: str, map_id: str) -> None:
    m = _require_map(session, campaign_id, map_id)
    entity = session.get(Entity, m.entity_id)
    session.execute(delete(MapMarker).where(MapMarker.map_id == m.entity_id))
    session.execute(delete(MapRegion).where(MapRegion.map_id == m.entity_id))
    session.delete(m)
    if entity is not None:
        session.delete(entity)  # a map entity has no article/history worth soft-deleting
    session.commit()


# --------------------------------------------------------------------------- #
# Entity image attachments (gallery)
# --------------------------------------------------------------------------- #
class EntityNotFound(AtlasError):
    pass


class AttachmentNotFound(AtlasError):
    pass


def _attachment_out(session: Session, att: EntityMedia) -> AttachmentOut:
    media = session.get(Media, att.media_id)
    return AttachmentOut(
        id=att.id, entity_id=att.entity_id, media_id=att.media_id,
        filename=media.filename if media else "", mime=media.mime if media else "",
        caption=att.caption, sort_order=att.sort_order,
    )


def _require_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.campaign_id != campaign_id:
        raise EntityNotFound("entity not found")
    return entity


def list_attachments(session: Session, campaign_id: str, entity_id: str) -> list[AttachmentOut]:
    rows = session.scalars(
        select(EntityMedia)
        .where(EntityMedia.campaign_id == campaign_id, EntityMedia.entity_id == entity_id)
        .order_by(EntityMedia.sort_order, EntityMedia.created_at_real)
    )
    return [_attachment_out(session, r) for r in rows]


def attach_media(
    session: Session,
    campaign: Campaign,
    entity_id: str,
    *,
    data: bytes,
    filename: str,
    caption: str | None,
) -> AttachmentOut:
    _require_entity(session, campaign.id, entity_id)
    media = store_media_bytes(session, campaign.id, data, filename=filename, kind="image")
    next_order = (
        session.execute(
            select(func.coalesce(func.max(EntityMedia.sort_order), -1) + 1).where(
                EntityMedia.entity_id == entity_id
            )
        ).scalar_one()
    )
    att = EntityMedia(
        id=new_id(), campaign_id=campaign.id, entity_id=entity_id, media_id=media.id,
        caption=caption or None, sort_order=int(next_order), created_at_real=now_real_iso(),
    )
    session.add(att)
    session.commit()
    return _attachment_out(session, att)


def _require_attachment(session: Session, campaign_id: str, entity_id: str, attachment_id: str) -> EntityMedia:
    att = session.get(EntityMedia, attachment_id)
    if att is None or att.campaign_id != campaign_id or att.entity_id != entity_id:
        raise AttachmentNotFound("attachment not found")
    return att


def media_for_attachment(session: Session, campaign_id: str, entity_id: str, attachment_id: str) -> Media:
    att = _require_attachment(session, campaign_id, entity_id, attachment_id)
    media = session.get(Media, att.media_id)
    if media is None:  # pragma: no cover - db drift
        raise AttachmentNotFound("attachment media missing")
    return media


def delete_attachment(session: Session, campaign_id: str, entity_id: str, attachment_id: str) -> None:
    att = _require_attachment(session, campaign_id, entity_id, attachment_id)
    session.delete(att)  # leave the content-addressed file (shared, backup-covered)
    session.commit()


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #
def add_marker(
    session: Session, campaign_id: str, map_id: str, data: MarkerCreate
) -> MarkerOut:
    _require_map(session, campaign_id, map_id)
    _validate_targets(session, campaign_id, data.target_entity_id, data.child_map_id)
    marker = MapMarker(
        id=new_id(), map_id=map_id, x=data.x, y=data.y, icon=data.icon, color=data.color,
        note=data.note, layer=data.layer, target_entity_id=data.target_entity_id,
        child_map_id=data.child_map_id,
    )
    session.add(marker)
    session.commit()
    return _marker_out(session, marker)


def update_marker(
    session: Session, campaign_id: str, map_id: str, marker_id: str, data: MarkerUpdate
) -> MarkerOut:
    marker = _require_marker(session, campaign_id, map_id, marker_id)
    fields = data.model_dump(exclude_unset=True)
    _validate_targets(
        session, campaign_id,
        fields.get("target_entity_id", marker.target_entity_id),
        fields.get("child_map_id", marker.child_map_id),
    )
    for key, value in fields.items():
        setattr(marker, key, value)
    session.commit()
    return _marker_out(session, marker)


def delete_marker(session: Session, campaign_id: str, map_id: str, marker_id: str) -> None:
    marker = _require_marker(session, campaign_id, map_id, marker_id)
    session.delete(marker)
    session.commit()


def _require_marker(
    session: Session, campaign_id: str, map_id: str, marker_id: str
) -> MapMarker:
    _require_map(session, campaign_id, map_id)
    marker = session.get(MapMarker, marker_id)
    if marker is None or marker.map_id != map_id:
        raise MapNotFound(marker_id)
    return marker


def _validate_targets(
    session: Session, campaign_id: str, target_entity_id: str | None, child_map_id: str | None
) -> None:
    if target_entity_id:
        ent = session.get(Entity, target_entity_id)
        if ent is None or ent.campaign_id != campaign_id:
            raise AtlasError("target entity not found in this campaign")
    if child_map_id:
        _require_map(session, campaign_id, child_map_id)


# --------------------------------------------------------------------------- #
# Regions (polygons)
# --------------------------------------------------------------------------- #
def _require_region(
    session: Session, campaign_id: str, map_id: str, region_id: str
) -> MapRegion:
    _require_map(session, campaign_id, map_id)
    region = session.get(MapRegion, region_id)
    if region is None or region.map_id != map_id:
        raise MapNotFound(region_id)
    return region


def add_region(
    session: Session, campaign_id: str, map_id: str, data: RegionCreate
) -> RegionOut:
    _require_map(session, campaign_id, map_id)
    _validate_targets(session, campaign_id, data.target_entity_id, data.child_map_id)
    region = MapRegion(
        id=new_id(), map_id=map_id, name=data.name,
        polygon_json=json.dumps([list(p) for p in data.polygon]),
        color=data.color, note=data.note, layer=data.layer,
        target_entity_id=data.target_entity_id, child_map_id=data.child_map_id,
    )
    session.add(region)
    session.commit()
    return _region_out(session, region)


def update_region(
    session: Session, campaign_id: str, map_id: str, region_id: str, data: RegionUpdate
) -> RegionOut:
    region = _require_region(session, campaign_id, map_id, region_id)
    fields = data.model_dump(exclude_unset=True)
    _validate_targets(
        session, campaign_id,
        fields.get("target_entity_id", region.target_entity_id),
        fields.get("child_map_id", region.child_map_id),
    )
    if "polygon" in fields and fields["polygon"] is not None:
        region.polygon_json = json.dumps([list(p) for p in fields.pop("polygon")])
    else:
        fields.pop("polygon", None)
    for key, value in fields.items():
        setattr(region, key, value)
    session.commit()
    return _region_out(session, region)


def delete_region(session: Session, campaign_id: str, map_id: str, region_id: str) -> None:
    region = _require_region(session, campaign_id, map_id, region_id)
    session.delete(region)
    session.commit()
