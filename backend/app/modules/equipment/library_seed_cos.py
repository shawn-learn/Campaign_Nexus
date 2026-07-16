"""Curse of Strahd equipment, seeded into the shared library (source ``"cos"``).

Sourced from ``cos/magic-items.md`` in the repo. The named artifacts carry the
campaign's own mechanics summary; the standard items reference their location and
sourcebook page rather than reproducing published descriptions.

Idempotent: keyed by ``(name, source="cos")`` like the SRD starter seed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.equipment.models import LibraryEntry

SEED_SOURCE = "cos"

# (name, rarity, requires_attunement, properties, summary)
_NAMED: list[tuple[str, str | None, bool, str, str]] = [
    ("Blood Spear", "uncommon", False,
     "+2 spear (1d6 piercing). On a hit that drops an enemy to 0 HP, gain 2d6 temporary HP. Only the chosen character gets the +2.",
     "Found in area Y2 (Yester Hill)."),
    ("Bloodhorn's Pelt", "uncommon", False,
     "Worn as a cape/robe over other armour. Berserkers won't attack you or your party unless provoked.",
     "Found at Tsolenka Pass."),
    ("Gulthias Staff", "rare", True,
     "Quarterstaff (1d6 bludgeoning), 10 charges (regain 1d6+4 at dusk). Evil plants ignore you until you attack. On hit, spend a charge to heal equal to damage dealt (target then makes a DC 12 WIS save or gains short-term madness). Break the staff to kill all blights within 300 ft.",
     "Found at W16 (Loading Winch), Old Bonegrinder / winery area."),
    ("Rebenaxt", "uncommon", False,
     "+0 battleaxe (1d8 slashing) — magical but no bonus. Deals an extra 1d8 slashing to plants and plant creatures. Wielded by a non-good creature, thorns deal 1 damage to the attacker. (Custom name; unnamed in source.)",
     "Found at Y4, the Gulthias Tree (Yester Hill)."),
    ("Saint Markovia's Thighbone", "rare", True,
     "Mace (1d6). Sheds bright light 20 ft / dim 20 ft. On hitting a fiend or undead, deal an extra 2d6 radiant; if it drops to 25 HP or less it must make a DC 15 WIS save or be destroyed (Frightened on a save). Crumbles to dust after an encounter in which it strikes a vampire or spawn.",
     "Found at K84, Crypt 6 (Castle Ravenloft)."),
    ("Shield of the Order", "rare", False,
     "+2 shield. The bearer gains +2 to initiative while conscious.",
     "Found at K41, the Treasury (Castle Ravenloft)."),
    ("Statuette of Saint Markovia", "uncommon", False,
     "When held by a good creature, grants +1 to all saving throws.",
     "Found at S15f (Abbey of Saint Markovia)."),
    ("Sunsword", "legendary", True,
     "+2 longsword (1d8 radiant), finesse; usable by anyone proficient with short or long swords. Sentient (INT 11, WIS 17, CHA 16; sees/hears 60 ft). Emits 15 ft bright sunlight + 15 ft dim; bonus action to ignite the blade; action to adjust the radius (5–45 ft). Extra 1d8 radiant to undead on a hit.",
     "The legendary weapon against Strahd."),
    ("Vindicta", "rare", True,
     "+1 shortsword (1d6 piercing). Sentient and dedicated to fighting evil (INT 11, WIS 13, CHA 13; sees/hears 120 ft); attunes only to a lawful good creature. Emits 15 ft bright + 15 ft dim light. Once per dawn, cast crusader's mantle on yourself. (Custom name; unnamed in source.)",
     "Found at K74H (Castle Ravenloft)."),
]

# Standard items from the Misc. table — name, rarity, attunement, location, page ref.
_STANDARD: list[tuple[str, str | None, bool, str, str]] = [
    ("Alchemy Jug", "uncommon", False, "K41 (Treasury)", "DMG 150"),
    ("Bag of Tricks", "uncommon", False, "N2h (Ravens' Loft)", "DMG 154"),
    ("Deck of Illusions", "uncommon", False, "K84, Crypt 9", "DMG 161"),
    ("Doss Lute", "rare", True, "K36 (Dining Hall of the Count)", "DMG 176 (Instrument of the Bards)"),
    ("+2 Greatsword", "rare", False, "Q36 (Dragon's Audience Hall — Vladimir)", "PHB 149"),
    ("Hat of Disguise", "uncommon", True, "Rictavio", "DMG 173"),
    ("Helm of Brilliance", "very_rare", True, "K41 (Treasury)", "DMG 173"),
    ("Icon of Ravenloft", "legendary", True, "K15 (Chapel)", "CoS 222"),
    ("Luck Blade", "legendary", True, "K84, Crypt 29", "DMG 179"),
    ("Mace of Terror", "rare", True, "K15 (Chapel)", "DMG 180"),
    ("Oil of Sharpness", "very_rare", False, "U3 (Baba Lysaga's Hut)", "DMG 184"),
    ("Pipes of Haunting", "uncommon", False, "U3 (Baba Lysaga's Hut)", "DMG 185"),
    ("+2 Plate Armour", "very_rare", False, "K85 (Sergei's Tomb)", "PHB 145"),
    ("Ring of Mind Shielding", "uncommon", True, "Rictavio", "DMG 191"),
    ("Ring of Regeneration", "very_rare", True, "S7 (Abbey Graveyard)", "DMG 191"),
    ("Ring of Warmth", "uncommon", True, "N9a (Kasimir's Hovel)", "DMG 193"),
    ("Robe of Useful Items", "uncommon", False, "X5a (God of Secrets)", "DMG 195"),
    ("+1 Rod of the Pact Keeper", "uncommon", True, "K41 (Treasury)", "DMG 197"),
    ("Staff of Frost", "very_rare", True, "X17 (Upper West Hall)", "DMG 202"),
    ("Staff of Power", "very_rare", True, "K84, Crypt 15", "DMG 202"),
    ("Stone of Good Luck", "uncommon", True, "U3 (Baba Lysaga's Hut)", "DMG 205 (Luckstone)"),
    ("Tome of Understanding", "very_rare", False, "X20 (Architect's Room)", "DMG 209"),
    ("Wand of Secrets", "uncommon", False, "X2b (Guard Room)", "DMG 211"),
]


def _entries() -> list[LibraryEntry]:
    rows: list[LibraryEntry] = []
    for name, rarity, attune, properties, summary in _NAMED:
        rows.append(LibraryEntry(
            id=new_id(), name=name, summary=summary, item_type="magical",
            rarity=rarity, requires_attunement=attune, properties=properties,
            source=SEED_SOURCE,
        ))
    for name, rarity, attune, location, page in _STANDARD:
        rows.append(LibraryEntry(
            id=new_id(), name=name, summary=f"Found at {location}. See {page}.",
            item_type="magical", rarity=rarity, requires_attunement=attune,
            properties=None, source=SEED_SOURCE,
        ))
    return rows


def ensure_seeded(session: Session) -> int:
    """Insert any missing Curse of Strahd entries. Returns the number newly added."""
    existing = set(
        session.scalars(
            select(LibraryEntry.name).where(LibraryEntry.source == SEED_SOURCE)
        )
    )
    added = 0
    for entry in _entries():
        if entry.name in existing:
            continue
        session.add(entry)
        added += 1
    if added:
        session.commit()
    return added
