from __future__ import annotations

from pydantic import BaseModel, Field


class MerchantOut(BaseModel):
    entity_id: str
    name: str
    summary: str | None
    npc_id: str | None
    npc_name: str | None
    location_id: str | None
    location_name: str | None
    buyback_pct: int
    stock_count: int


class MerchantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    npc_id: str | None = None
    location_id: str | None = None
    buyback_pct: int = Field(default=50, ge=0, le=1000)


class MerchantUpdate(BaseModel):
    name: str | None = None
    summary: str | None = None
    npc_id: str | None = None
    location_id: str | None = None
    buyback_pct: int | None = Field(default=None, ge=0, le=1000)
    #: Explicit clear flags — None means "unchanged", so these allow unsetting a link.
    clear_npc: bool = False
    clear_location: bool = False


class StockLineOut(BaseModel):
    id: str
    merchant_id: str
    library_id: str
    name: str
    item_type: str
    rarity: str | None
    requires_attunement: bool
    price_cp: int
    price_label: str
    quantity: int | None
    notes: str | None


class StockLineCreate(BaseModel):
    library_id: str
    #: Sale price. Either a coin string ("2 sp") or copper via ``price_cp``.
    price: str | None = None
    price_cp: int | None = None
    quantity: int | None = None
    notes: str | None = None


class StockLineUpdate(BaseModel):
    price: str | None = None
    price_cp: int | None = None
    quantity: int | None = None
    notes: str | None = None
    clear_quantity: bool = False


class PurchaseIn(BaseModel):
    #: How many units the party buys (must be <= remaining stock if limited).
    quantity: int = Field(default=1, ge=1)
    #: Optional label for the created copy (e.g. "from Bildrath").
    instance_label: str | None = None


class PurchaseResult(BaseModel):
    item_ids: list[str]
    total_cp: int
    total_label: str
    party_gold: int          # whole-gp view (compat)
    party_wealth_cp: int
    party_wealth_label: str


class SellbackIn(BaseModel):
    item_id: str


class SellbackResult(BaseModel):
    credited_cp: int
    credited_label: str
    credited_gp: int         # whole-gp view (compat)
    party_gold: int
    party_wealth_cp: int
    party_wealth_label: str
