from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.equipment import service
from app.modules.equipment.schemas import (
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

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


def _404_eq(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "equipment not found")


def _404_item(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "item not found")


def _404_lib(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or "library entry not found")


# ---------------------------------------------------------------------------
# Equipment library (global, campaign-independent) router
# ---------------------------------------------------------------------------

library_router = APIRouter(prefix="/api/v1/equipment-library", tags=["equipment-library"])


@library_router.get("", response_model=list[LibraryEntryOut])
def list_library(
    item_type: str | None = Query(default=None),
    rarity: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[LibraryEntryOut]:
    return service.list_library(session, item_type=item_type, rarity=rarity, q=q)


@library_router.post("", response_model=LibraryEntryOut, status_code=status.HTTP_201_CREATED)
def create_library_entry(
    body: LibraryEntryCreate,
    session: Session = Depends(get_session),
) -> LibraryEntryOut:
    try:
        return service.create_library_entry(session, body)
    except service.EquipmentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@library_router.get("/{entry_id}", response_model=LibraryEntryOut)
def get_library_entry(
    entry_id: str,
    session: Session = Depends(get_session),
) -> LibraryEntryOut:
    try:
        return service.get_library_entry(session, entry_id)
    except service.LibraryEntryNotFound as exc:
        raise _404_lib(exc) from exc


@library_router.patch("/{entry_id}", response_model=LibraryEntryOut)
def update_library_entry(
    entry_id: str,
    body: LibraryEntryUpdate,
    session: Session = Depends(get_session),
) -> LibraryEntryOut:
    try:
        return service.update_library_entry(session, entry_id, body)
    except service.LibraryEntryNotFound as exc:
        raise _404_lib(exc) from exc
    except service.EquipmentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@library_router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_entry(
    entry_id: str,
    session: Session = Depends(get_session),
) -> None:
    try:
        service.delete_library_entry(session, entry_id)
    except service.LibraryEntryNotFound as exc:
        raise _404_lib(exc) from exc


# ---------------------------------------------------------------------------
# Equipment (catalog) router
# ---------------------------------------------------------------------------

equipment_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/equipment",
    tags=["equipment"],
)


@equipment_router.get("", response_model=list[EquipmentOut])
def list_equipment(
    item_type: str | None = Query(default=None),
    rarity: str | None = Query(default=None),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[EquipmentOut]:
    return service.list_equipment(session, ctx.campaign_id, item_type=item_type, rarity=rarity)


@equipment_router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def create_equipment(
    body: EquipmentCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EquipmentOut:
    try:
        return service.create_equipment(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except service.EquipmentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@equipment_router.post("/import", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def import_from_library(
    body: ImportFromLibrary,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EquipmentOut:
    """Copy a library template into this campaign as a new definition."""
    try:
        return service.import_from_library(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except service.LibraryEntryNotFound as exc:
        raise _404_lib(exc) from exc
    except service.EquipmentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@equipment_router.post("/{equip_id}/save-to-library", response_model=LibraryEntryOut,
                       status_code=status.HTTP_201_CREATED)
def save_to_library(
    equip_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> LibraryEntryOut:
    """Publish a campaign definition into the shared library as a custom template."""
    try:
        return service.save_to_library(session, ctx.campaign_id, equip_id)
    except service.EquipmentNotFound as exc:
        raise _404_eq(exc) from exc


@equipment_router.get("/{equip_id}", response_model=EquipmentOut)
def get_equipment(
    equip_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> EquipmentOut:
    try:
        return service.get_equipment(session, ctx.campaign_id, equip_id)
    except service.EquipmentNotFound as exc:
        raise _404_eq(exc) from exc


@equipment_router.patch("/{equip_id}", response_model=EquipmentOut)
def update_equipment(
    equip_id: str,
    body: EquipmentUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EquipmentOut:
    try:
        return service.update_equipment(session, ctx.campaign_id, equip_id, body)
    except service.EquipmentNotFound as exc:
        raise _404_eq(exc) from exc


@equipment_router.delete("/{equip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(
    equip_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    """Soft-delete the backing wiki entity.

    Soft delete does *not* fire the FK cascade, so the ``Item`` copies survive in
    the table; ``list_items``/``get_item`` filter them out by joining to the
    (now-deleted) definition.
    """
    from app.modules.wiki import service as wiki_service
    try:
        service.get_equipment(session, ctx.campaign_id, equip_id)
        wiki_service.soft_delete_entity(session, ctx.campaign_id, equip_id)
    except service.EquipmentNotFound as exc:
        raise _404_eq(exc) from exc


@equipment_router.get("/{equip_id}/items", response_model=list[ItemInstanceOut])
def list_equipment_items(
    equip_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[ItemInstanceOut]:
    """All copies of a specific equipment definition."""
    try:
        service.get_equipment(session, ctx.campaign_id, equip_id)
    except service.EquipmentNotFound as exc:
        raise _404_eq(exc) from exc
    return service.list_items(session, ctx.campaign_id, equipment_id=equip_id)


# ---------------------------------------------------------------------------
# Item (instance) router
# ---------------------------------------------------------------------------

items_router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}/items",
    tags=["items"],
)


@items_router.get("", response_model=list[ItemInstanceOut])
def list_items(
    equipment_id: str | None = Query(default=None),
    holder_type: str | None = Query(default=None),
    holder_id: str | None = Query(default=None),
    location_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[ItemInstanceOut]:
    return service.list_items(
        session, ctx.campaign_id,
        equipment_id=equipment_id,
        holder_type=holder_type,
        holder_id=holder_id,
        location_id=location_id,
    )


@items_router.post("", response_model=ItemInstanceOut, status_code=status.HTTP_201_CREATED)
def create_item(
    body: ItemInstanceCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ItemInstanceOut:
    try:
        return service.create_item(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except (service.EquipmentNotFound, service.EquipmentError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@items_router.get("/{item_id}", response_model=ItemInstanceOut)
def get_item(
    item_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> ItemInstanceOut:
    try:
        return service.get_item(session, ctx.campaign_id, item_id)
    except service.ItemNotFound as exc:
        raise _404_item(exc) from exc


@items_router.patch("/{item_id}", response_model=ItemInstanceOut)
def update_item(
    item_id: str,
    body: ItemInstanceUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ItemInstanceOut:
    try:
        return service.update_item(session, ctx.campaign_id, item_id, body)
    except service.ItemNotFound as exc:
        raise _404_item(exc) from exc


@items_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_item(session, _campaign(session, ctx.campaign_id), item_id)
    except service.ItemNotFound as exc:
        raise _404_item(exc) from exc


@items_router.post("/{item_id}/transfer", response_model=ItemInstanceOut)
def transfer_item(
    item_id: str,
    body: TransferIn,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> ItemInstanceOut:
    try:
        return service.transfer_item(
            session, _campaign(session, ctx.campaign_id), item_id, body
        )
    except service.ItemNotFound as exc:
        raise _404_item(exc) from exc
    except service.EquipmentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@items_router.get("/{item_id}/history", response_model=list[OwnershipRow])
def get_item_history(
    item_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[OwnershipRow]:
    try:
        return service.ownership_history(
            session, _campaign(session, ctx.campaign_id), item_id
        )
    except service.ItemNotFound as exc:
        raise _404_item(exc) from exc
