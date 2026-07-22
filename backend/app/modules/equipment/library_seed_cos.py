"""Curse of Strahd equipment, seeded into the shared library (source ``"cos"``).

Magic items are sourced from ``cos/magic-items.md`` in the repo. The named
artifacts carry the campaign's own mechanics summary; the standard items
reference their location and sourcebook page rather than reproducing published
descriptions. ``_MUNDANE`` covers named, non-magical props found while reading
the rest of the ``cos/`` notes (plot documents, personal effects, trap
triggers) that aren't in the Magic Items appendix but are still worth tracking.

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
    ("Tome of Strahd", None, False,
     "A narrative journal detailing Strahd's transformation into a vampire and his obsession with Tatyana. Reading it takes 8 hours and reveals Strahd's history, the Amber Temple, and the nature of his curse.",
     "Fortune of Ravenloft — placement is set by Madam Eva's Tarokka reading."),
    ("Holy Symbol of Ravenkind", "legendary", True,
     "A platinum amulet shaped like a sun with a central crystal; attunes only to a good-aligned cleric or paladin. 10 charges: 1 charge as an action to hold vampires and vampire spawn within 30 ft (DC 15 WIS save); 3 charges to add a +3 bonus to a Turn Undead DC; 7 charges to shed true sunlight in a 30 ft radius for 10 minutes.",
     "Fortune of Ravenloft — placement is set by Madam Eva's Tarokka reading."),
    ("Bones of St. Andral", None, False,
     "Plot item. The saint's remains consecrate St. Andral's Church in Vallaki; while they are missing, the church loses its protection and vampire spawn can enter. Restoring them to the crypt reconsecrates the ground.",
     "Stolen by Henrik van der Voort and hidden at N6 (Coffin Maker's Shop)."),
    ("Magic Mirror of Summon Assassin", None, False,
     "A cursed full-length mirror. A creature that looks into it sees a bridal figure; the mirror then summons an assassin-like phantom that attacks the viewer.",
     "Found at N3p (Bridal Gown and Spirit Mirror), Burgomaster's Mansion, Vallaki."),
    ("Victor's Spellbook", None, False,
     "Victor Vallakovich's spellbook. Contains the spells he has mastered plus his notes on the unstable teleportation circle he is building in the attic.",
     "Found at N3t (Victor's Workroom), Burgomaster's Mansion, Vallaki."),
    ("Kasimir's Spellbook", None, False,
     "A leather-bound book: the dusk elf Kasimir Velikov's spellbook. It holds every spell "
     "he has prepared as a mage (Appendix D / MM base template) plus the extras named in his "
     "hovel description. Cantrips: fire bolt, light, mage hand, prestidigitation. 1st: arcane "
     "lock, comprehend languages, detect magic, identify, mage armor, magic missile, shield. "
     "2nd: darkness (added by his hovel text), invisibility, locate object, misty step, "
     "suggestion. 3rd: counterspell, dispel magic, fireball, fly, nondetection. 4th: greater "
     "invisibility, polymorph. 5th: cone of cold, legend lore. Errata removed ray of frost "
     "from his list.",
     "Kept inside Kasimir's hovel at N9a, the dusk elf encampment southwest of Vallaki."),
    ("Vial of Cackle Fever", None, False,
     "A stoppered vial of the disease cackle fever, brewed by the night hags. A creature exposed to it makes a DC 13 CON save or is infected (INT-based, causes fits of laughter).",
     "Held by the night hags at O1 (Old Bonegrinder)."),
    ("Sunsword", "legendary", True,
     "+2 longsword (1d8 radiant), finesse; usable by anyone proficient with short or long swords. Sentient (INT 11, WIS 17, CHA 16; sees/hears 60 ft). Emits 15 ft bright sunlight + 15 ft dim; bonus action to ignite the blade; action to adjust the radius (5–45 ft). Extra 1d8 radiant to undead on a hit.",
     "The legendary weapon against Strahd."),
    ("Vindicta", "rare", True,
     "+1 shortsword (1d6 piercing). Sentient and dedicated to fighting evil (INT 11, WIS 13, CHA 13; sees/hears 120 ft); attunes only to a lawful good creature. Emits 15 ft bright + 15 ft dim light. Once per dawn, cast crusader's mantle on yourself. (Custom name; unnamed in source.)",
     "Found at K74H (Castle Ravenloft)."),
    ("Khazan's Phylactery", "legendary", False,
     "The demilich Khazan's phylactery. While it survives, his remains (a skull in K84, Crypt 15) can reconstitute him. Destructible only by a strike from the Staff of Power.",
     "Hidden behind a suit of armour at Van Richten's Tower."),
    ("Magic Gem (Yester Hill)", "uncommon", False,
     "Custom item (reflavoured Cone of Regeneration): 1 charge, regained at dawn. As an action, spend the charge to cast regeneration (PHB p. 271) on a creature you touch.",
     "One of three gems stolen from the Wizard of Wines. Embedded in the Druids' Strahd statue (Y3)."),
    ("Magic Gem (Ruins of Berez)", "uncommon", False,
     "Custom item (reflavoured Cone of Regeneration): 1 charge, regained at dawn. As an action, spend the charge to cast regeneration (PHB p. 271) on a creature you touch.",
     "One of three gems stolen from the Wizard of Wines. Kept in Baba Lysaga's hut (U3)."),
    ("Magic Gem (Lost)", "uncommon", False,
     "Custom item (reflavoured Cone of Regeneration): 1 charge, regained at dawn. As an action, spend the charge to cast regeneration (PHB p. 271) on a creature you touch.",
     "One of three gems stolen from the Wizard of Wines. Its whereabouts are deliberately left a mystery — a hook for a custom side-quest."),
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
    ("Tasha's Holy Symbol", "rare", True, "K84, Crypt 11", "CoS 223"),
    ("Elixir of Health", "rare", False, "N2h (Ravens' Loft)", "DMG 168"),
    ("Potion of Healing", "common", False, "N2h (Ravens' Loft)", "DMG 187"),
    ("Potion of Greater Healing", "uncommon", False, "K68 (Guards' Run)", "DMG 187"),
    ("Potion of Superior Healing", "rare", False, "S15 (Abbey Main Hall)", "DMG 187"),
    ("Potion of Invulnerability", "rare", True, "Q28 (Wine Cellar)", "DMG 188"),
    ("Potion of Youth", "rare", False, "O1 (Old Bonegrinder)", "DMG 188"),
    ("Pale Tincture", None, False, "O1 (Old Bonegrinder)", "DMG 258 (poison)"),
    ("Scroll of Heroes' Feast", "rare", False, "S16 (Abbot's Nursery)", "DMG 200"),
    ("Spell Scroll (Mass Cure Wounds)", "rare", False, "U3 (Baba Lysaga's Hut)", "DMG 200"),
    ("Spell Scroll (Revivify)", "uncommon", False, "U3 (Baba Lysaga's Hut)", "DMG 200"),
    ("Spell Scroll (Protection from Fiends)", "rare", False, "Rictavio's wagon (Van Richten's Tower)", "DMG 200"),
    ("Spell Scroll (Protection from Undead)", "rare", False, "Rictavio's wagon (Van Richten's Tower)", "DMG 200"),
    ("Spell Scroll (Major Image)", "uncommon", False, "Ezmerelda's wagon (Van Richten's Tower)", "DMG 200"),
    ("Spell Scroll (Remove Curse)", "uncommon", False, "Ezmerelda's wagon (Van Richten's Tower)", "DMG 200"),
    ("Spell Scroll (Raise Dead)", "rare", False, "Carried by Rictavio (Rudolph van Richten)", "DMG 200"),
    ("Broom of Animated Attack", "uncommon", False, "Death House / Castle Ravenloft", "CoS 226"),
    ("Amulet of Proof against Detection and Location", "uncommon", True, "K40 (Castle Ravenloft)", "DMG 150"),
    ("Cloak of Protection", "uncommon", True, "K40 (Castle Ravenloft)", "DMG 159"),
    ("Manual of Flesh Golems", "very_rare", True, "S17 (Abbot's quarters, Abbey of Saint Markovia)", "DMG 199 (Manual of Golems)"),
]

# CoS-specific mundane props — not magic items, but named/plot-relevant enough to track.
_MUNDANE: list[tuple[str, str]] = [
    ("Deed to the Mill", "A legal deed to Old Bonegrinder, found in Death House. Presenting it "
     "(with a successful DC 20 Persuasion/Intimidation check) convinces the night hags to vacate "
     "peacefully instead of fighting for the mill."),
    ("Groom Figurine", "A small decorative figurine in the Dining Hall of the Count (K36). Removing "
     "it from the room summons an invisible stalker to hunt down whoever took it."),
    ("Stone Carving of a Walrus", "A carved keepsake found during a search of the Abbot's quarters "
     "(S17) — the only remaining evidence of his mortal life before he was made a deva."),
    ("Ezmerelda's Prosthetic Leg", "Ezmerelda d'Avenir's wooden prosthetic leg. If Strahd captures "
     "and tortures her, it's torn off and discarded nearby; without it she can't walk unassisted."),
    ("Flamboyant Vistani Wagon", "Ezmerelda's covered wagon. Knowing its command words lets the party "
     "drive it at a fast pace (4 mph) with no penalty; it sleeps the whole party but can't be taken "
     "into the deep Barovian woods."),
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
    for name, summary in _MUNDANE:
        rows.append(LibraryEntry(
            id=new_id(), name=name, summary=summary, item_type="mundane",
            rarity=None, requires_attunement=False, properties=None,
            source=SEED_SOURCE,
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
