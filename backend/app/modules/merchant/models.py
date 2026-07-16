from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Merchant(Base):
    """A shop, backed by an ``Entity`` of type ``"merchant"``.

    Optionally linked to the shopkeeper (``npc_id``) and the storefront
    (``location_id``). ``buyback_pct`` is the percentage of an item's value the
    shop pays when buying it back from the party (default 50%).
    """

    __tablename__ = "merchant"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The shopkeeper NPC and/or the storefront location (both optional).
    npc_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True, index=True
    )
    buyback_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=50)


class MerchantStock(Base):
    """One for-sale line in a merchant's inventory.

    References a shared ``equipment_library`` template. ``price_cp`` is the sale
    price in copper pieces (the shop's price, which may differ from the template's
    listed value). ``quantity`` NULL means unlimited stock.
    """

    __tablename__ = "merchant_stock"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String, ForeignKey("merchant.entity_id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    library_id: Mapped[str] = mapped_column(
        String, ForeignKey("equipment_library.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Sale price in copper pieces (1 gp = 100 cp).
    price_cp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: NULL = unlimited stock; otherwise units remaining.
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
