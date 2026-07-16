"""Standard adventuring goods (the shop price list) seeded into the library.

Prices are the campaign's listed shop prices. Deduped by **name across all
sources** so this never duplicates an item the starter/CoS seeds already added.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.equipment.models import LibraryEntry

SEED_SOURCE = "phb"

# (name, price string) — all mundane gear.
_GOODS: list[tuple[str, str]] = [
    ("Abacus", "2 sp"), ("Acid (vial)", "250 gp"), ("Arrows (20)", "10 gp"),
    ("Blowgun Needles (50)", "10 gp"), ("Crossbow Bolts (20)", "10 gp"),
    ("Sling Bullets (20)", "4 sp"), ("Arcane Focus (Crystal)", "100 gp"),
    ("Arcane Focus (Orb)", "200 gp"), ("Arcane Focus (Rod)", "100 gp"),
    ("Arcane Focus (Staff)", "50 gp"), ("Arcane Focus (Wand)", "100 gp"),
    ("Backpack", "20 gp"), ("Ball Bearings (Bag of 1,000)", "10 gp"),
    ("Barrel", "20 gp"), ("Basket", "4 ep"), ("Bedroll", "10 gp"), ("Bell", "10 gp"),
    ("Blanket", "5 ep"), ("Block and Tackle", "10 gp"), ("Book", "250 gp"),
    ("Bottle, Glass", "20 gp"), ("Bucket", "5 sp"), ("Caltrops (Bag of 20)", "10 gp"),
    ("Candle", "1 sp"), ("Case, Crossbow Bolt", "10 gp"), ("Case, Map or Scroll", "10 gp"),
    ("Chain (10 feet)", "50 gp"), ("Chalk (1 piece)", "1 sp"), ("Chest", "50 gp"),
    ("Climber's Kit", "250 gp"), ("Clothes, Common", "5 ep"), ("Clothes, Costume", "50 gp"),
    ("Clothes, Fine", "150 gp"), ("Clothes, Traveler's", "20 gp"), ("Crowbar", "20 gp"),
    ("Druidic Focus (Sprig of Mistletoe)", "10 gp"), ("Druidic Focus (Totem)", "10 gp"),
    ("Druidic Focus (Wooden Staff)", "50 gp"), ("Druidic Focus (Yew Wand)", "100 gp"),
    ("Fishing Tackle", "10 gp"), ("Flask/Tankard", "2 sp"), ("Grappling Hook", "20 gp"),
    ("Hammer", "10 gp"), ("Hammer, Sledge", "20 gp"), ("Healer's Kit", "50 gp"),
    ("Holy Symbol (Amulet)", "50 gp"), ("Holy Symbol (Emblem)", "50 gp"),
    ("Holy Symbol (Reliquary)", "50 gp"), ("Holy Water (Flask)", "250 gp"),
    ("Hourglass", "250 gp"), ("Hunting Trap", "50 gp"), ("Ink (1 ounce bottle)", "100 gp"),
    ("Ink Pen", "2 sp"), ("Jug/Pitcher", "2 sp"), ("Ladder (10-foot)", "1 ep"),
    ("Lantern, Bullseye", "100 gp"), ("Lantern, Hooded", "50 gp"), ("Lock", "100 gp"),
    ("Manacles", "20 gp"), ("Mess Kit", "2 ep"), ("Mirror, Steel", "50 gp"),
    ("Oil (Flask)", "1 ep"), ("Paper (1 sheet)", "2 ep"), ("Parchment (1 sheet)", "1 ep"),
    ("Perfume (Vial)", "50 gp"), ("Pick, Miner's", "20 gp"), ("Piton", "5 sp"),
    ("Pole (10-foot)", "5 sp"), ("Pot, Iron", "20 gp"), ("Pouch", "5 ep"),
    ("Quiver", "10 gp"), ("Ram, Portable", "40 gp"), ("Rations (1 day)", "5 ep"),
    ("Robes", "10 gp"), ("Rope, Hempen (50 feet)", "10 gp"), ("Rope, Silk (50 feet)", "100 gp"),
    ("Sack", "1 sp"), ("Scale, Merchant's", "50 gp"), ("Sealing Wax", "5 ep"),
    ("Shovel", "20 gp"), ("Signal Whistle", "5 sp"), ("Signet Ring", "50 gp"),
    ("Soap", "2 sp"), ("Spikes, Iron (10)", "10 gp"), ("Tent, Two-Person", "20 gp"),
    ("Tinderbox", "5 ep"), ("Torch", "1 sp"), ("Vial", "10 gp"), ("Waterskin", "2 ep"),
    ("Whetstone", "1 sp"),
]


def ensure_seeded(session: Session) -> int:
    """Insert any goods not already present (by name, any source). Returns count added."""
    existing = set(session.scalars(select(LibraryEntry.name)))
    added = 0
    for name, price in _GOODS:
        if name in existing:
            continue
        session.add(LibraryEntry(
            id=new_id(), name=name, item_type="mundane", value_gp=price,
            requires_attunement=False, source=SEED_SOURCE,
        ))
        existing.add(name)
        added += 1
    if added:
        session.commit()
    return added
