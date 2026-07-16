"""Equipment projectors - maintain Item cached columns + ownership history.

Handles ``item_transferred``: closes the open ownership interval, opens a new
one, and updates ``Item.current_holder_*`` / ``current_location_id``.

Idempotent under replay - ``reset_equipment_projections`` clears all derived
state and the event fold re-derives it deterministically.
"""

from __future__ import annotations

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.event_bus import EventRecord
from app.core.ids import new_id
from app.core.projections import register_projector, register_reset
from app.modules.equipment.models import Item, ItemOwnershipHistory


def _item(session: Session, campaign_id: str, item_id: str) -> Item | None:
    item = session.get(Item, item_id)
    return item if item is not None and item.campaign_id == campaign_id else None


def _transferred(session: Session, event: EventRecord) -> None:
    item_id = event.payload.get("item_id")
    if not isinstance(item_id, str):
        return
    item = _item(session, event.campaign_id, item_id)
    if item is None:
        return

    holder_type = event.payload.get("to_holder_type")
    holder_type = str(holder_type) if isinstance(holder_type, str) else None
    holder_id = event.payload.get("to_holder_id")
    holder_id = str(holder_id) if isinstance(holder_id, str) else None
    location_id = event.payload.get("location_id")
    location_id = str(location_id) if isinstance(location_id, str) else None

    # Close the currently-open interval
    session.execute(
        update(ItemOwnershipHistory)
        .where(
            ItemOwnershipHistory.item_id == item_id,
            ItemOwnershipHistory.to_game.is_(None),
        )
        .values(to_game=event.occurred_at_game)
    )
    # Open the new interval
    session.add(ItemOwnershipHistory(
        id=new_id(),
        campaign_id=event.campaign_id,
        item_id=item_id,
        holder_type=holder_type,
        holder_id=holder_id,
        location_id=location_id,
        from_game=event.occurred_at_game,
        to_game=None,
        cause_event_id=event.id,
    ))
    # Update the cached projection columns on the Item copy
    item.current_holder_type = holder_type
    item.current_holder_id = holder_id
    item.current_location_id = location_id
    session.flush()


_HANDLERS = {
    "item_transferred": _transferred,
}


def equipment_projector(session: Session, event: EventRecord) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is not None:
        handler(session, event)


def reset_equipment_projections(session: Session, campaign_id: str | None) -> None:
    """Wipe derived equipment state before a replay."""
    history = delete(ItemOwnershipHistory)
    items = update(Item).values(
        current_holder_type=None, current_holder_id=None, current_location_id=None
    )
    if campaign_id:
        history = history.where(ItemOwnershipHistory.campaign_id == campaign_id)
        items = items.where(Item.campaign_id == campaign_id)
    session.execute(history)
    session.execute(items)


def register() -> None:
    register_projector(equipment_projector)
    register_reset(reset_equipment_projections)


register()
