"""Starter equipment library — a small set of standard gear and common magic
items seeded into the global library so it is useful out of the box.

Idempotent: entries are keyed by ``(name, source="srd")`` and only inserted when
absent, so adding new rows here ships them on the next startup without
duplicating existing ones or clobbering GM edits.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.equipment.models import LibraryEntry

SEED_SOURCE = "srd"

# (name, item_type, rarity, requires_attunement, value_gp, weight_lb, properties)
_SEED: list[tuple[str, str, str | None, bool, str | None, float | None, str]] = [
    # -- Adventuring gear (mundane) ------------------------------------------
    ("Backpack", "mundane", None, False, "2 gp", 5.0, "Holds roughly 1 cubic foot / 30 lb of gear."),
    ("Bedroll", "mundane", None, False, "1 gp", 7.0, "For resting outdoors."),
    ("Rations (1 day)", "mundane", None, False, "5 sp", 2.0, "Dry food for one day of travel."),
    ("Waterskin", "mundane", None, False, "2 sp", 5.0, "Holds about 4 pints of liquid when full."),
    ("Torch", "mundane", None, False, "1 cp", 1.0, "Sheds bright light in a short radius for about an hour."),
    ("Hooded Lantern", "mundane", None, False, "5 gp", 2.0, "Bright light nearby, dim beyond; can be shuttered."),
    ("Tinderbox", "mundane", None, False, "5 sp", 1.0, "Flint, steel, and tinder for lighting fires."),
    ("Rope (50 ft, hempen)", "mundane", None, False, "1 gp", 10.0, "Can be burst with a hard Strength check."),
    ("Grappling Hook", "mundane", None, False, "2 gp", 4.0, "Anchors a rope to a ledge or beam."),
    ("Crowbar", "mundane", None, False, "2 gp", 5.0, "Grants advantage on Strength checks where leverage helps."),
    ("Healer's Kit", "mundane", None, False, "5 gp", 3.0, "Ten uses; stabilises a dying creature without a check."),
    ("Thieves' Tools", "mundane", None, False, "25 gp", 1.0, "Picks and files for disarming traps and picking locks."),
    # -- Weapons (mundane) ---------------------------------------------------
    ("Dagger", "mundane", None, False, "2 gp", 1.0, "1d4 piercing; finesse, light, thrown (20/60)."),
    ("Longsword", "mundane", None, False, "15 gp", 3.0, "1d8 slashing; versatile (1d10)."),
    ("Greataxe", "mundane", None, False, "30 gp", 7.0, "1d12 slashing; heavy, two-handed."),
    ("Shortbow", "mundane", None, False, "25 gp", 2.0, "1d6 piercing; ammunition (80/320), two-handed."),
    # -- Armor (mundane) -----------------------------------------------------
    ("Leather Armor", "mundane", None, False, "10 gp", 10.0, "Light armor; AC 11 + Dex modifier."),
    ("Chain Mail", "mundane", None, False, "75 gp", 55.0, "Heavy armor; AC 16, Str 13, stealth disadvantage."),
    ("Shield", "mundane", None, False, "10 gp", 6.0, "+2 AC while wielded."),
    # -- Common / uncommon magic items --------------------------------------
    ("Potion of Healing", "magical", "common", False, "50 gp", 0.5, "Drink to regain 2d4 + 2 hit points."),
    ("Potion of Greater Healing", "magical", "uncommon", False, "150 gp", 0.5, "Drink to regain 4d4 + 4 hit points."),
    ("Bag of Holding", "magical", "uncommon", False, None, 15.0, "Holds far more than its size; interior is an extradimensional space."),
    ("Driftglobe", "magical", "uncommon", False, None, 1.0, "Floating globe that sheds light on command."),
    ("Cloak of Elvenkind", "magical", "uncommon", True, None, 1.0, "Advantage on Stealth to hide; disadvantage to those trying to see you."),
    ("Immovable Rod", "magical", "uncommon", False, None, 2.0, "Fixes itself in place in the air, holding up to 8,000 lb."),
]


def ensure_seeded(session: Session) -> int:
    """Insert any missing starter entries. Returns the number newly added."""
    existing = set(
        session.scalars(
            select(LibraryEntry.name).where(LibraryEntry.source == SEED_SOURCE)
        )
    )
    added = 0
    for name, item_type, rarity, attune, value_gp, weight_lb, properties in _SEED:
        if name in existing:
            continue
        session.add(LibraryEntry(
            id=new_id(), name=name, item_type=item_type, rarity=rarity,
            requires_attunement=attune, value_gp=value_gp, weight_lb=weight_lb,
            properties=properties, source=SEED_SOURCE,
        ))
        added += 1
    if added:
        session.commit()
    return added
