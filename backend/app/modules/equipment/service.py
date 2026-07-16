"""Equipment service - catalog CRUD + item instance management.

Two distinct command families:
  * Equipment (catalog): create/update/list/get a *definition*.
  * Item (instance): create/update/transfer/list/get individual *copies*.

Every instance ownership change is recorded as ``item_transferred``; the
projector maintains the cached holder columns and the full history timeline.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.equipment.models import Equipment, Item, ItemOwnershipHistory, LibraryEntry
from app.modules.equipment.schemas import (
    HOLDER_TYPES,
    ITEM_TYPES,
    RARITIES,
    EquipmentCreate,
    EquipmentOut,
    EquipmentUpdate,
    ImportFromLibrary,
    ItemInstanceCreate,
    ItemInstanceOut,
    ItemInstanceUpdate,
    LibraryEntryCreate,
    LibraryEntryOut,
    LibraryEntryUpdate,
    OwnershipRow,
    TransferIn,
)
from app.modules.time import service as time_service
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate


class EquipmentError(ValueError):
    pass


class EquipmentNotFound(LookupError):
    pass


class ItemNotFound(LookupError):
    pass


class LibraryEntryNotFound(LookupError):
    pass


# ---------------------------------------------------------------------------
# Equipment library (global templates)
# ---------------------------------------------------------------------------

def _lib_out(entry: LibraryEntry) -> LibraryEntryOut:
    return LibraryEntryOut(
        id=entry.id, name=entry.name, summary=entry.summary,
        item_type=entry.item_type, rarity=entry.rarity,
        requires_attunement=bool(entry.requires_attunement),
        value_gp=entry.value_gp, weight_lb=entry.weight_lb,
        properties=entry.properties, attunement_notes=entry.attunement_notes,
        source=entry.source,
    )


def _req_library_entry(session: Session, entry_id: str) -> LibraryEntry:
    entry = session.get(LibraryEntry, entry_id)
    if entry is None:
        raise LibraryEntryNotFound(entry_id)
    return entry


def list_library(
    session: Session, *,
    item_type: str | None = None, rarity: str | None = None, q: str | None = None,
) -> list[LibraryEntryOut]:
    stmt = select(LibraryEntry)
    if item_type:
        stmt = stmt.where(LibraryEntry.item_type == item_type)
    if rarity:
        stmt = stmt.where(LibraryEntry.rarity == rarity)
    if q:
        stmt = stmt.where(LibraryEntry.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(LibraryEntry.name)
    return [_lib_out(e) for e in session.scalars(stmt)]


def get_library_entry(session: Session, entry_id: str) -> LibraryEntryOut:
    return _lib_out(_req_library_entry(session, entry_id))


def create_library_entry(
    session: Session, data: LibraryEntryCreate, *, source: str = "custom"
) -> LibraryEntryOut:
    _validate_type(data.item_type)
    _validate_rarity(data.rarity)
    entry = LibraryEntry(
        id=new_id(), name=data.name, summary=data.summary,
        item_type=data.item_type, rarity=data.rarity,
        requires_attunement=data.requires_attunement,
        value_gp=data.value_gp, weight_lb=data.weight_lb,
        properties=data.properties, attunement_notes=data.attunement_notes,
        source=source,
    )
    session.add(entry)
    session.commit()
    return _lib_out(entry)


def update_library_entry(
    session: Session, entry_id: str, data: LibraryEntryUpdate
) -> LibraryEntryOut:
    entry = _req_library_entry(session, entry_id)
    updates = data.model_dump(exclude_unset=True)
    if "item_type" in updates and updates["item_type"] is not None:
        _validate_type(updates["item_type"])
    if "rarity" in updates:
        _validate_rarity(updates["rarity"])
    for key, value in updates.items():
        setattr(entry, key, value)
    session.commit()
    return _lib_out(entry)


def delete_library_entry(session: Session, entry_id: str) -> None:
    entry = _req_library_entry(session, entry_id)
    session.delete(entry)
    session.commit()


def import_from_library(
    session: Session, campaign: Campaign, data: ImportFromLibrary, *, created_by: str
) -> EquipmentOut:
    """Materialise a library template as a campaign-owned ``Equipment`` definition.

    Idempotent per campaign: if this template was already imported, the existing
    definition is returned rather than creating a duplicate.
    """
    entry = _req_library_entry(session, data.library_id)
    existing = session.scalars(
        select(Equipment).where(
            Equipment.campaign_id == campaign.id,
            Equipment.library_id == entry.id,
        )
    ).first()
    if existing is not None:
        return get_equipment(session, campaign.id, existing.entity_id)
    return create_equipment(
        session, campaign,
        EquipmentCreate(
            name=entry.name, summary=entry.summary, item_type=entry.item_type,
            rarity=entry.rarity, requires_attunement=bool(entry.requires_attunement),
            value_gp=entry.value_gp, weight_lb=entry.weight_lb,
            properties=entry.properties, attunement_notes=entry.attunement_notes,
        ),
        created_by=created_by, library_id=entry.id,
    )


def save_to_library(
    session: Session, campaign_id: str, equip_id: str
) -> LibraryEntryOut:
    """Push a campaign definition up into the shared library as a custom template."""
    eq = _req_equipment(session, campaign_id, equip_id)
    entity = _entity(session, eq.entity_id)
    return create_library_entry(
        session,
        LibraryEntryCreate(
            name=entity.name, summary=entity.summary, item_type=eq.item_type,
            rarity=eq.rarity, requires_attunement=bool(eq.requires_attunement),
            value_gp=eq.value_gp, weight_lb=eq.weight_lb,
            properties=eq.properties, attunement_notes=eq.attunement_notes,
        ),
        source="custom",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _req_equipment(session: Session, campaign_id: str, equip_id: str) -> Equipment:
    eq = session.get(Equipment, equip_id)
    if eq is None or eq.campaign_id != campaign_id:
        raise EquipmentNotFound(equip_id)
    return eq


def _req_item(session: Session, campaign_id: str, item_id: str) -> Item:
    item = session.get(Item, item_id)
    if item is None or item.campaign_id != campaign_id:
        raise ItemNotFound(item_id)
    # A copy whose catalog definition was soft-deleted is treated as gone too.
    definition = session.get(Entity, item.equipment_id)
    if definition is None or definition.deleted_at_real is not None:
        raise ItemNotFound(item_id)
    return item


def _entity(session: Session, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise EquipmentNotFound(entity_id)
    return entity


def _name_of(session: Session, entity_id: str | None) -> str | None:
    if entity_id is None:
        return None
    entity = session.get(Entity, entity_id)
    return entity.name if entity is not None else None


def _instance_count(session: Session, equip_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(Item).where(Item.equipment_id == equip_id)
    ) or 0


def _eq_out(session: Session, eq: Equipment) -> EquipmentOut:
    entity = _entity(session, eq.entity_id)
    return EquipmentOut(
        entity_id=eq.entity_id,
        name=entity.name,
        summary=entity.summary,
        item_type=eq.item_type,
        rarity=eq.rarity,
        requires_attunement=bool(eq.requires_attunement),
        value_gp=eq.value_gp,
        weight_lb=float(eq.weight_lb) if eq.weight_lb is not None else None,
        properties=eq.properties,
        attunement_notes=eq.attunement_notes,
        instance_count=_instance_count(session, eq.entity_id),
        library_id=eq.library_id,
    )


def _item_out(session: Session, item: Item) -> ItemInstanceOut:
    eq = session.get(Equipment, item.equipment_id)
    eq_entity = _entity(session, item.equipment_id) if eq else None
    holder_name: str | None = None
    if item.current_holder_type == "party":
        holder_name = "Party"
    elif item.current_holder_id:
        holder_name = _name_of(session, item.current_holder_id)
    return ItemInstanceOut(
        item_id=item.id,
        equipment_id=item.equipment_id,
        equipment_name=eq_entity.name if eq_entity else "Unknown",
        item_type=eq.item_type if eq else "mundane",
        rarity=eq.rarity if eq else None,
        requires_attunement=bool(eq.requires_attunement) if eq else False,
        value_gp=eq.value_gp if eq else None,
        instance_label=item.instance_label,
        notes=item.notes,
        current_holder_type=item.current_holder_type,
        current_holder_id=item.current_holder_id,
        current_holder_name=holder_name,
        current_location_id=item.current_location_id,
        current_location_name=_name_of(session, item.current_location_id),
    )


def _validate_type(item_type: str) -> None:
    if item_type not in ITEM_TYPES:
        raise EquipmentError(f"unknown item_type: {item_type!r}")


def _validate_rarity(rarity: str | None) -> None:
    if rarity is not None and rarity not in RARITIES:
        raise EquipmentError(f"unknown rarity: {rarity!r}")


def _validate_holder(holder_type: str | None, holder_id: str | None) -> None:
    if holder_type is not None and holder_type not in HOLDER_TYPES:
        raise EquipmentError(f"unknown holder_type: {holder_type!r}")
    if holder_type in ("pc", "npc", "location") and not holder_id:
        raise EquipmentError(f"holder_id required when holder_type is {holder_type!r}")
    if holder_type in (None, "party", "unowned") and holder_id:
        raise EquipmentError(f"holder_id not allowed when holder_type is {holder_type!r}")


# ---------------------------------------------------------------------------
# Equipment (catalog) reads
# ---------------------------------------------------------------------------

def get_equipment(session: Session, campaign_id: str, equip_id: str) -> EquipmentOut:
    return _eq_out(session, _req_equipment(session, campaign_id, equip_id))


def list_equipment(
    session: Session,
    campaign_id: str,
    *,
    item_type: str | None = None,
    rarity: str | None = None,
) -> list[EquipmentOut]:
    stmt = (
        select(Equipment)
        .where(Equipment.campaign_id == campaign_id)
        .join(Entity, Entity.id == Equipment.entity_id)
        .where(Entity.deleted_at_real.is_(None))
    )
    if item_type:
        stmt = stmt.where(Equipment.item_type == item_type)
    if rarity:
        stmt = stmt.where(Equipment.rarity == rarity)
    rows = list(session.scalars(stmt))
    rows.sort(key=lambda e: _entity(session, e.entity_id).name)
    return [_eq_out(session, e) for e in rows]


# ---------------------------------------------------------------------------
# Equipment (catalog) commands
# ---------------------------------------------------------------------------

def create_equipment(
    session: Session, campaign: Campaign, data: EquipmentCreate, *,
    created_by: str, library_id: str | None = None,
) -> EquipmentOut:
    _validate_type(data.item_type)
    _validate_rarity(data.rarity)
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="equipment", name=data.name, summary=data.summary),
        created_by=created_by,
    )
    session.add(Equipment(
        entity_id=entity.id, campaign_id=campaign.id, library_id=library_id,
        item_type=data.item_type, rarity=data.rarity,
        requires_attunement=data.requires_attunement,
        value_gp=data.value_gp, weight_lb=data.weight_lb,
        properties=data.properties, attunement_notes=data.attunement_notes,
    ))
    session.commit()
    return get_equipment(session, campaign.id, entity.id)


def update_equipment(
    session: Session, campaign_id: str, equip_id: str, data: EquipmentUpdate
) -> EquipmentOut:
    eq = _req_equipment(session, campaign_id, equip_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(eq, key, value)
    session.commit()
    return get_equipment(session, campaign_id, equip_id)


# ---------------------------------------------------------------------------
# Item (instance) reads
# ---------------------------------------------------------------------------

def get_item(session: Session, campaign_id: str, item_id: str) -> ItemInstanceOut:
    return _item_out(session, _req_item(session, campaign_id, item_id))


def list_items(
    session: Session,
    campaign_id: str,
    *,
    equipment_id: str | None = None,
    holder_type: str | None = None,
    holder_id: str | None = None,
    location_id: str | None = None,
) -> list[ItemInstanceOut]:
    stmt = (
        select(Item)
        .where(Item.campaign_id == campaign_id)
        # Hide copies whose catalog definition has been soft-deleted (its FK
        # cascade never fires on a soft delete, so the rows survive).
        .join(Entity, Entity.id == Item.equipment_id)
        .where(Entity.deleted_at_real.is_(None))
    )
    if equipment_id:
        stmt = stmt.where(Item.equipment_id == equipment_id)
    if holder_type:
        stmt = stmt.where(Item.current_holder_type == holder_type)
    if holder_id:
        stmt = stmt.where(Item.current_holder_id == holder_id)
    if location_id:
        stmt = stmt.where(Item.current_location_id == location_id)
    items = list(session.scalars(stmt))
    return [_item_out(session, i) for i in items]


def ownership_history(
    session: Session, campaign: Campaign, item_id: str
) -> list[OwnershipRow]:
    _req_item(session, campaign.id, item_id)
    cal = time_service.calendar_for(campaign)
    rows = session.scalars(
        select(ItemOwnershipHistory)
        .where(ItemOwnershipHistory.item_id == item_id)
        .order_by(ItemOwnershipHistory.from_game)
    )
    result = []
    for row in rows:
        holder_name: str | None = None
        if row.holder_type == "party":
            holder_name = "Party"
        elif row.holder_id:
            holder_name = _name_of(session, row.holder_id)
        result.append(OwnershipRow(
            holder_type=row.holder_type,
            holder_id=row.holder_id,
            holder_name=holder_name,
            location_id=row.location_id,
            location_name=_name_of(session, row.location_id),
            from_game=row.from_game,
            from_label=cal.format(row.from_game)["label"],
            to_game=row.to_game,
            to_label=cal.format(row.to_game)["label"] if row.to_game is not None else None,
        ))
    return result


# ---------------------------------------------------------------------------
# Item (instance) commands
# ---------------------------------------------------------------------------

def _do_transfer(
    session: Session, campaign: Campaign, item: Item,
    *, holder_type: str, holder_id: str | None,
    location_id: str | None, reason: str | None,
) -> None:
    eq_entity = _entity(session, item.equipment_id)
    label = item.instance_label or eq_entity.name
    from_type = item.current_holder_type
    from_id = item.current_holder_id

    from_desc = "unowned" if from_type in (None, "unowned") else (
        "the party" if from_type == "party" else (_name_of(session, from_id) or from_type)
    )
    to_desc = "unowned" if holder_type in (None, "unowned") else (
        "the party" if holder_type == "party" else (_name_of(session, holder_id) or holder_type)
    )
    suffix = f" ({reason})" if reason else ""

    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "item_transferred",
            payload={
                "item_id": item.id,
                "from_holder_type": from_type,
                "from_holder_id": from_id,
                "to_holder_type": holder_type,
                "to_holder_id": holder_id,
                "location_id": location_id,
                "reason": reason,
            },
            narrative=f"{label} transferred from {from_desc} to {to_desc}{suffix}.",
            subject_entity_ids=(item.equipment_id,),
        )


def create_item(
    session: Session, campaign: Campaign, data: ItemInstanceCreate, *, created_by: str
) -> ItemInstanceOut:
    _req_equipment(session, campaign.id, data.equipment_id)
    _validate_holder(data.initial_holder_type, data.initial_holder_id)

    if data.initial_holder_id is not None:
        target = session.get(Entity, data.initial_holder_id)
        if target is None or target.campaign_id != campaign.id:
            raise EquipmentError("holder entity not found in this campaign")
    if data.initial_location_id is not None:
        loc = session.get(Entity, data.initial_location_id)
        if loc is None or loc.campaign_id != campaign.id:
            raise EquipmentError("location not found in this campaign")

    item_id = new_id()
    holder_type = data.initial_holder_type or "unowned"
    item = Item(
        id=item_id,
        equipment_id=data.equipment_id,
        campaign_id=campaign.id,
        instance_label=data.instance_label,
        notes=data.notes,
        current_holder_type=holder_type,
        current_holder_id=data.initial_holder_id,
        current_location_id=data.initial_location_id,
    )
    session.add(item)
    session.commit()

    # Record initial placement as the first ownership event
    _do_transfer(
        session, campaign, item,
        holder_type=holder_type,
        holder_id=data.initial_holder_id,
        location_id=data.initial_location_id,
        reason="added",
    )
    return get_item(session, campaign.id, item_id)


def update_item(
    session: Session, campaign_id: str, item_id: str, data: ItemInstanceUpdate
) -> ItemInstanceOut:
    item = _req_item(session, campaign_id, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    return get_item(session, campaign_id, item_id)


def delete_item(session: Session, campaign: Campaign, item_id: str) -> None:
    """Remove a physical copy from the world.

    The ``Item`` row is a structural record (created directly, not folded from an
    event), so removal is a real delete rather than a projection reset. We still
    emit an ``item_removed`` event first so the deletion is auditable in the event
    log even after the row and its history are gone (FK cascade).
    """
    item = _req_item(session, campaign.id, item_id)
    label = item.instance_label or _entity(session, item.equipment_id).name
    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "item_removed",
            payload={"item_id": item.id, "equipment_id": item.equipment_id},
            narrative=f"{label} was removed from the campaign.",
            subject_entity_ids=(item.equipment_id,),
        )
    session.delete(item)
    session.commit()


def transfer_item(
    session: Session, campaign: Campaign, item_id: str, data: TransferIn
) -> ItemInstanceOut:
    item = _req_item(session, campaign.id, item_id)
    holder_type = data.holder_type or "unowned"
    _validate_holder(holder_type, data.holder_id)

    if data.holder_id is not None:
        target = session.get(Entity, data.holder_id)
        if target is None or target.campaign_id != campaign.id:
            raise EquipmentError("holder entity not found in this campaign")
    if data.location_id is not None:
        loc = session.get(Entity, data.location_id)
        if loc is None or loc.campaign_id != campaign.id:
            raise EquipmentError("location not found in this campaign")

    _do_transfer(
        session, campaign, item,
        holder_type=holder_type,
        holder_id=data.holder_id,
        location_id=data.location_id,
        reason=data.reason,
    )
    return get_item(session, campaign.id, item_id)
