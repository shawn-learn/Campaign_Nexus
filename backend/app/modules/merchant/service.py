"""Merchant service — shops, inventory, and buy/sell against the party's gold."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.money import format_coins, format_cp, parse_cp
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.equipment import service as equipment_service
from app.modules.equipment.models import LibraryEntry
from app.modules.equipment.schemas import ImportFromLibrary, ItemInstanceCreate
from app.modules.merchant.models import Merchant, MerchantStock
from app.modules.merchant.schemas import (
    MerchantCreate,
    MerchantOut,
    MerchantUpdate,
    PurchaseIn,
    PurchaseResult,
    SellbackIn,
    SellbackResult,
    StockLineCreate,
    StockLineOut,
    StockLineUpdate,
)
from app.modules.playbook import service as party_service
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate


class MerchantError(ValueError):
    pass


class MerchantNotFound(LookupError):
    pass


class StockNotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _name_of(session: Session, entity_id: str | None) -> str | None:
    if entity_id is None:
        return None
    entity = session.get(Entity, entity_id)
    return entity.name if entity is not None else None


def _req_merchant(session: Session, campaign_id: str, merchant_id: str) -> Merchant:
    m = session.get(Merchant, merchant_id)
    if m is None or m.campaign_id != campaign_id:
        raise MerchantNotFound(merchant_id)
    entity = session.get(Entity, m.entity_id)
    if entity is None or entity.deleted_at_real is not None:
        raise MerchantNotFound(merchant_id)
    return m


def _req_stock(session: Session, campaign_id: str, line_id: str) -> MerchantStock:
    line = session.get(MerchantStock, line_id)
    if line is None or line.campaign_id != campaign_id:
        raise StockNotFound(line_id)
    return line


def _req_library(session: Session, library_id: str) -> LibraryEntry:
    entry = session.get(LibraryEntry, library_id)
    if entry is None:
        raise MerchantError("library template not found")
    return entry


def _stock_count(session: Session, merchant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(MerchantStock).where(MerchantStock.merchant_id == merchant_id)
    ) or 0


def _merchant_out(session: Session, m: Merchant) -> MerchantOut:
    entity = session.get(Entity, m.entity_id)
    return MerchantOut(
        entity_id=m.entity_id,
        name=entity.name if entity else "Unknown",
        summary=entity.summary if entity else None,
        npc_id=m.npc_id,
        npc_name=_name_of(session, m.npc_id),
        location_id=m.location_id,
        location_name=_name_of(session, m.location_id),
        buyback_pct=m.buyback_pct,
        stock_count=_stock_count(session, m.entity_id),
    )


def _stock_out(session: Session, line: MerchantStock) -> StockLineOut:
    lib = session.get(LibraryEntry, line.library_id)
    return StockLineOut(
        id=line.id,
        merchant_id=line.merchant_id,
        library_id=line.library_id,
        name=lib.name if lib else "Unknown",
        item_type=lib.item_type if lib else "mundane",
        rarity=lib.rarity if lib else None,
        requires_attunement=bool(lib.requires_attunement) if lib else False,
        price_cp=line.price_cp,
        price_label=format_cp(line.price_cp),
        quantity=line.quantity,
        notes=line.notes,
    )


def _validate_link(session: Session, campaign_id: str, entity_id: str | None) -> None:
    if entity_id is None:
        return
    entity = session.get(Entity, entity_id)
    if entity is None or entity.campaign_id != campaign_id:
        raise MerchantError("linked entity not found in this campaign")


def _resolve_price_cp(data_price: str | None, data_price_cp: int | None, lib: LibraryEntry) -> int:
    if data_price_cp is not None:
        return max(0, data_price_cp)
    if data_price:
        parsed = parse_cp(data_price)
        if parsed is None:
            raise MerchantError(f"couldn't read price {data_price!r} (try e.g. '2 sp' or '15 gp')")
        return parsed
    return parse_cp(lib.value_gp) or 0


# --------------------------------------------------------------------------- #
# Merchant CRUD
# --------------------------------------------------------------------------- #

def list_merchants(session: Session, campaign_id: str) -> list[MerchantOut]:
    stmt = (
        select(Merchant)
        .where(Merchant.campaign_id == campaign_id)
        .join(Entity, Entity.id == Merchant.entity_id)
        .where(Entity.deleted_at_real.is_(None))
    )
    rows = list(session.scalars(stmt))
    rows.sort(key=lambda m: (_name_of(session, m.entity_id) or "").lower())
    return [_merchant_out(session, m) for m in rows]


def get_merchant(session: Session, campaign_id: str, merchant_id: str) -> MerchantOut:
    return _merchant_out(session, _req_merchant(session, campaign_id, merchant_id))


def create_merchant(
    session: Session, campaign: Campaign, data: MerchantCreate, *, created_by: str
) -> MerchantOut:
    _validate_link(session, campaign.id, data.npc_id)
    _validate_link(session, campaign.id, data.location_id)
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="merchant", name=data.name, summary=data.summary),
        created_by=created_by,
    )
    session.add(Merchant(
        entity_id=entity.id, campaign_id=campaign.id,
        npc_id=data.npc_id, location_id=data.location_id, buyback_pct=data.buyback_pct,
    ))
    session.commit()
    return get_merchant(session, campaign.id, entity.id)


def update_merchant(
    session: Session, campaign_id: str, merchant_id: str, data: MerchantUpdate
) -> MerchantOut:
    m = _req_merchant(session, campaign_id, merchant_id)
    if data.npc_id is not None:
        _validate_link(session, campaign_id, data.npc_id)
        m.npc_id = data.npc_id
    if data.clear_npc:
        m.npc_id = None
    if data.location_id is not None:
        _validate_link(session, campaign_id, data.location_id)
        m.location_id = data.location_id
    if data.clear_location:
        m.location_id = None
    if data.buyback_pct is not None:
        m.buyback_pct = data.buyback_pct
    if data.name is not None or data.summary is not None:
        entity = session.get(Entity, m.entity_id)
        if entity is not None:
            if data.name is not None:
                entity.name = data.name
            if data.summary is not None:
                entity.summary = data.summary or None
    session.commit()
    return get_merchant(session, campaign_id, merchant_id)


def delete_merchant(session: Session, campaign_id: str, merchant_id: str, *, deleted_by: str) -> None:
    m = _req_merchant(session, campaign_id, merchant_id)
    session.execute(delete(MerchantStock).where(MerchantStock.merchant_id == m.entity_id))
    session.commit()
    wiki_service.soft_delete_entity(session, campaign_id, m.entity_id)


# --------------------------------------------------------------------------- #
# Stock CRUD
# --------------------------------------------------------------------------- #

def list_stock(session: Session, campaign_id: str, merchant_id: str) -> list[StockLineOut]:
    _req_merchant(session, campaign_id, merchant_id)
    rows = session.scalars(
        select(MerchantStock).where(MerchantStock.merchant_id == merchant_id)
    )
    lines = [_stock_out(session, line) for line in rows]
    lines.sort(key=lambda s: s.name.lower())
    return lines


def add_stock(
    session: Session, campaign: Campaign, merchant_id: str, data: StockLineCreate
) -> StockLineOut:
    _req_merchant(session, campaign.id, merchant_id)
    lib = _req_library(session, data.library_id)
    line = MerchantStock(
        id=new_id(), merchant_id=merchant_id, campaign_id=campaign.id,
        library_id=lib.id, price_cp=_resolve_price_cp(data.price, data.price_cp, lib),
        quantity=data.quantity, notes=data.notes,
    )
    session.add(line)
    session.commit()
    return _stock_out(session, line)


def update_stock(
    session: Session, campaign_id: str, line_id: str, data: StockLineUpdate
) -> StockLineOut:
    line = _req_stock(session, campaign_id, line_id)
    if data.price_cp is not None:
        line.price_cp = max(0, data.price_cp)
    elif data.price is not None:
        parsed = parse_cp(data.price)
        if parsed is None:
            raise MerchantError(f"couldn't read price {data.price!r}")
        line.price_cp = parsed
    if data.quantity is not None:
        line.quantity = data.quantity
    if data.clear_quantity:
        line.quantity = None
    if data.notes is not None:
        line.notes = data.notes or None
    session.commit()
    return _stock_out(session, line)


def remove_stock(session: Session, campaign_id: str, line_id: str) -> None:
    line = _req_stock(session, campaign_id, line_id)
    session.delete(line)
    session.commit()


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #

def purchase(
    session: Session, campaign: Campaign, merchant_id: str, line_id: str, data: PurchaseIn,
    *, created_by: str,
) -> PurchaseResult:
    merchant = _req_merchant(session, campaign.id, merchant_id)
    line = _req_stock(session, campaign.id, line_id)
    if line.merchant_id != merchant_id:
        raise StockNotFound(line_id)
    lib = _req_library(session, line.library_id)

    qty = data.quantity
    if line.quantity is not None and qty > line.quantity:
        raise MerchantError(f"only {line.quantity} left in stock")

    total_cp = line.price_cp * qty
    party = party_service.get_or_create_party(session, campaign.id)
    if party.wealth_cp < total_cp:
        raise MerchantError(
            f"the party can't afford this — needs {format_cp(total_cp)}, "
            f"has {format_coins(party.wealth_cp)}"
        )

    # Ensure a campaign definition exists (idempotent), then hand over the copies.
    eq = equipment_service.import_from_library(
        session, campaign, ImportFromLibrary(library_id=lib.id), created_by=created_by
    )
    item_ids: list[str] = []
    for _ in range(qty):
        created = equipment_service.create_item(
            session, campaign,
            ItemInstanceCreate(
                equipment_id=eq.entity_id, instance_label=data.instance_label,
                initial_holder_type="party",
            ),
            created_by=created_by,
        )
        item_ids.append(created.item_id)

    merchant_name = _name_of(session, merchant.entity_id) or "the merchant"
    with command_tx(session, campaign.id, actor="gm") as ctx:
        party.wealth_cp -= total_cp
        if line.quantity is not None:
            line.quantity -= qty
        ctx.emit(
            "item_purchased",
            payload={"merchant_id": merchant.entity_id, "library_id": lib.id,
                     "item_ids": item_ids, "quantity": qty, "cost_cp": total_cp},
            narrative=(
                f"The party bought {qty}× {lib.name} from {merchant_name} "  # noqa: RUF001
                f"for {format_cp(total_cp)}."
            ),
            subject_entity_ids=(merchant.entity_id,),
        )

    session.refresh(party)
    return PurchaseResult(
        item_ids=item_ids, total_cp=total_cp, total_label=format_cp(total_cp),
        party_gold=party.wealth_cp // 100, party_wealth_cp=party.wealth_cp,
        party_wealth_label=format_coins(party.wealth_cp),
    )


def sellback(
    session: Session, campaign: Campaign, merchant_id: str, data: SellbackIn
) -> SellbackResult:
    merchant = _req_merchant(session, campaign.id, merchant_id)
    item = equipment_service.get_item(session, campaign.id, data.item_id)  # raises ItemNotFound

    value_cp = parse_cp(item.value_gp) or 0
    credit_cp = value_cp * merchant.buyback_pct // 100

    party = party_service.get_or_create_party(session, campaign.id)
    merchant_name = _name_of(session, merchant.entity_id) or "the merchant"
    with command_tx(session, campaign.id, actor="gm") as ctx:
        party.wealth_cp += credit_cp
        ctx.emit(
            "item_sold",
            payload={"merchant_id": merchant.entity_id, "item_id": data.item_id,
                     "credit_cp": credit_cp},
            narrative=(
                f"The party sold {item.equipment_name} to {merchant_name} "
                f"for {format_cp(credit_cp)}."
            ),
            subject_entity_ids=(merchant.entity_id,),
        )
    # Remove the sold copy (emits its own item_removed audit event).
    equipment_service.delete_item(session, campaign, data.item_id)

    session.refresh(party)
    return SellbackResult(
        credited_cp=credit_cp, credited_label=format_cp(credit_cp),
        credited_gp=credit_cp // 100, party_gold=party.wealth_cp // 100,
        party_wealth_cp=party.wealth_cp, party_wealth_label=format_coins(party.wealth_cp),
    )
