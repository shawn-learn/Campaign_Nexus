"""Place the Curse of Strahd magic items — and a handful of named mundane
props — into the campaign.

Three stages, all idempotent:
  1. Ensure the shared library holds every CoS template (``library_seed_cos``).
  2. Import each template into the campaign catalog as an ``Equipment`` definition.
  3. Create the physical ``Item`` copies and place them with their holder/location.

The three Fortunes of Ravenloft (Tome of Strahd, Holy Symbol of Ravenkind,
Sunsword) are deliberately left *unowned* — Madam Eva's Tarokka reading decides
where they are at the start of the campaign. The third Winery gem (Magic Gem
(Lost)) is left unowned for the same reason: the Master Quest notes leave its
location a deliberate mystery.

Sub-areas the location tree doesn't model yet (the Abbey's S-areas, the Amber
Temple's X-areas, Berez's U3, Old Bonegrinder's O1, Yester Hill's Y-areas,
Van Richten's Tower's V-areas) are placed at their parent location, with the
book's area code kept in the copy's notes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.modules.equipment.projectors  # noqa: F401 — registers the ownership projector
from app.core.db import SessionLocal
from app.modules.campaign.models import Campaign
from app.modules.equipment import library_seed_cos
from app.modules.equipment import service as equipment_service
from app.modules.equipment.models import Equipment, Item, LibraryEntry
from app.modules.equipment.schemas import ImportFromLibrary, ItemInstanceCreate
from app.modules.wiki.models import Entity
from sqlalchemy import select

CAMPAIGN_ID = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd

# (library name, qty, holder_type, holder name, location name, instance_label, notes)
# holder name is an NPC entity name; location name is a location entity name.
PLACEMENTS: list[tuple[str, int, str, str | None, str | None, str | None, str]] = [
    # -- Fortunes of Ravenloft: placed by the Tarokka reading, not by the book --
    ("Tome of Strahd", 1, "unowned", None, None, None,
     "Fortune of Ravenloft. Location determined by Madam Eva's Tarokka reading."),
    ("Holy Symbol of Ravenkind", 1, "unowned", None, None, None,
     "Fortune of Ravenloft. Location determined by Madam Eva's Tarokka reading."),
    ("Sunsword", 1, "unowned", None, None, None,
     "Fortune of Ravenloft. Location determined by Madam Eva's Tarokka reading."),

    # -- Castle Ravenloft (Chapter 4) --
    ("Icon of Ravenloft", 1, "location", None, "K15. CHAPEL", None,
     "On the chapel altar (K15)."),
    ("Mace of Terror", 1, "location", None, "K15. CHAPEL", None, "K15 (Chapel)."),
    ("Alchemy Jug", 1, "location", None, "K41. TREASURY", None, "K41 (Treasury)."),
    ("Helm of Brilliance", 1, "location", None, "K41. TREASURY", None, "K41 (Treasury)."),
    ("+1 Rod of the Pact Keeper", 1, "location", None, "K41. TREASURY", None, "K41 (Treasury)."),
    ("Deck of Illusions", 1, "location", None, "K84. CATACOMBS", None, "K84, Crypt 9."),
    ("Tasha's Holy Symbol", 1, "location", None, "K84. CATACOMBS", None, "K84, Crypt 11."),
    ("Staff of Power", 1, "location", None, "K84. CATACOMBS", None, "K84, Crypt 15."),
    ("Luck Blade", 1, "location", None, "K84. CATACOMBS", None,
     "K84, Crypt 29. Contains 1 charge of the wish spell."),
    ("Saint Markovia's Thighbone", 1, "location", None, "K84. CATACOMBS", None, "K84, Crypt 6."),
    ("+2 Plate Armour", 1, "location", None, "K85. SERGEI'S TOMB", None, "K85 (Sergei's Tomb)."),
    ("Doss Lute", 1, "location", None, "K36. DINING HALL OF THE COUNT", None,
     "K36 (Dining Hall of the Count)."),
    ("Groom Figurine", 1, "location", None, "K36. DINING HALL OF THE COUNT", None,
     "K36 (Dining Hall of the Count). Removing it from the room summons an invisible stalker."),
    ("Shield of the Order", 1, "location", None, "K41. TREASURY", None, "K41 (Treasury)."),
    ("Vindicta", 1, "location", None, "Castle Ravenloft", None, "Found at K74H (Castle Ravenloft)."),
    ("Amulet of Proof against Detection and Location", 1, "location", None, "Castle Ravenloft", None, "Found in Castle Ravenloft (K40)."),
    ("Cloak of Protection", 1, "location", None, "Castle Ravenloft", None, "Found in Castle Ravenloft (K40)."),
    ("Ezmerelda's Prosthetic Leg", 1, "location", None, "K76. TORTURE CHAMBER", None,
     "Torn off and discarded here, underwater, if Strahd captures and tortures Ezmerelda."),

    # -- Death House (Chapter 2) --
    ("Deed to the Mill", 1, "location", None, "E7. Death House", None,
     "Lets the party legally claim Old Bonegrinder from the night hags on a successful "
     "DC 20 Persuasion/Intimidation check."),
    ("Broom of Animated Attack", 1, "location", None, "E7. Death House", None,
     "Found in Death House attic."),

    # -- Town of Vallaki (Chapter 5) --
    ("Hat of Disguise", 1, "npc", "Rudolph van Richten", "N2. BLUE WATER INN", None,
     "Carried by Rictavio (van Richten in disguise) at the Blue Water Inn."),
    ("Ring of Mind Shielding", 1, "npc", "Rudolph van Richten", "N2. BLUE WATER INN", None,
     "Carried by Rictavio (van Richten in disguise) at the Blue Water Inn."),
    ("Spell Scroll (Raise Dead)", 1, "npc", "Rudolph van Richten", "N2. BLUE WATER INN", None,
     "Carried by Rictavio (van Richten in disguise); potential quest reward for party renown."),
    ("Bag of Tricks", 1, "location", None, "N2H. RAVENS' LOFT", "Gray",
     "N2h (guest room / Ravens' Loft), Blue Water Inn."),
    ("Elixir of Health", 2, "location", None, "N2H. RAVENS' LOFT", None,
     "Hidden in N2h, Blue Water Inn."),
    ("Potion of Healing", 3, "location", None, "N2H. RAVENS' LOFT", None,
     "Hidden in N2h, Blue Water Inn."),
    ("Magic Mirror of Summon Assassin", 1, "location", None,
     "N3P. BRIDAL GOWN AND SPIRIT MIRROR", None,
     "N3p (closet), Burgomaster's Mansion."),
    ("Victor's Spellbook", 1, "location", None, "N3T. VICTOR'S WORKROOM", None,
     "N3t (attic workroom), Burgomaster's Mansion."),
    ("Ring of Warmth", 1, "npc", "Kasimir Velikov", "N9A. KASIMIR'S HOVEL", None,
     "Carried by Kasimir at the Vistani camp (N9a)."),
    ("Kasimir's Spellbook", 1, "location", None, "N9A. KASIMIR'S HOVEL", None,
     "N9a (Kasimir's hovel), in the dusk elf encampment southwest of Vallaki."),
    ("Bones of St. Andral", 1, "location", None, "N6. COFFIN MAKER'S SHOP", None,
     "Hidden in the attic of the coffin maker's shop (N6e/N6f)."),

    # -- Old Bonegrinder (Chapter 6) --
    ("Potion of Youth", 1, "npc", "Morgantha", "Old Bonegrinder", None,
     "In the night hags' possession (O1)."),
    ("Vial of Cackle Fever", 1, "npc", "Morgantha", "Old Bonegrinder", None,
     "In the night hags' possession (O1)."),
    ("Pale Tincture", 1, "npc", "Morgantha", "Old Bonegrinder", None,
     "In the night hags' possession (O1)."),

    # -- Argynvostholt (Chapter 7) --
    ("+2 Greatsword", 1, "npc", "Vladimir Horngaard", "Q36. DRAGON'S AUDIENCE HALL", None,
     "Wielded by Vladimir Horngaard (Q36)."),
    ("Potion of Invulnerability", 4, "location", None, "Q28. KNIGHTS' UARTERS", None,
     "Q28 (wine cellar)."),

    # -- Tsolenka Pass (Chapter 9) --
    ("Bloodhorn's Pelt", 1, "location", None, "Tsolenka Pass", None,
     "Found at Tsolenka Pass."),

    # -- Krezk & the Abbey of St. Markovia (Chapter 8) --
    ("Ring of Regeneration", 1, "location", None, "Village of Krezk", None,
     "Buried in the abbey graveyard (S7)."),
    ("Potion of Superior Healing", 1, "location", None, "Village of Krezk", None,
     "Abbey main hall (S15)."),
    ("Statuette of Saint Markovia", 1, "location", None, "Village of Krezk", None,
     "Found at S15f (Abbey of Saint Markovia)."),
    ("Scroll of Heroes' Feast", 1, "location", None, "Village of Krezk", None,
     "Abbot's nursery (S16)."),
    ("Stone Carving of a Walrus", 1, "location", None, "Village of Krezk", None,
     "Found searching S17, the Abbot's quarters. His one memento of his mortal life."),
    ("Manual of Flesh Golems", 1, "location", None, "Village of Krezk", None,
     "Found searching S17, the Abbot's quarters. Reading it deals 6d6 psychic damage to non-casters."),

    # -- Yester Hill (Chapter 14) --
    ("Blood Spear", 1, "location", None, "Yester Hill", None,
     "At the Gulthias Tree site."),
    ("Gulthias Staff", 1, "location", None, "Yester Hill", None,
     "Carried by the druid leader."),
    ("Rebenaxt", 1, "location", None, "Yester Hill", None,
     "Found at Y4, the Gulthias Tree site."),
    ("Magic Gem (Yester Hill)", 1, "location", None, "Yester Hill", None,
     "Embedded in the Druids' Strahd statue (Y3)."),

    # -- Ruins of Berez (Chapter 10) --
    ("Stone of Good Luck", 1, "location", None, "The Ruins of Berez", None,
     "Inside Baba Lysaga's creeping hut (U3)."),
    ("Oil of Sharpness", 1, "location", None, "The Ruins of Berez", None,
     "Inside Baba Lysaga's creeping hut (U3)."),
    ("Pipes of Haunting", 1, "location", None, "The Ruins of Berez", None,
     "Inside Baba Lysaga's creeping hut (U3)."),
    ("Spell Scroll (Mass Cure Wounds)", 1, "location", None, "The Ruins of Berez", None,
     "Inside Baba Lysaga's creeping hut (U3)."),
    ("Spell Scroll (Revivify)", 1, "location", None, "The Ruins of Berez", None,
     "Inside Baba Lysaga's creeping hut (U3)."),
    ("Magic Gem (Ruins of Berez)", 1, "location", None, "The Ruins of Berez", None,
     "Kept inside Baba Lysaga's creeping hut (U3)."),

    # -- Van Richten's Tower (Chapter 11) --
    ("Spell Scroll (Protection from Fiends)", 1, "location", None, "Van Richten's Tower", None,
     "Inside Rictavio's carnival wagon outside the tower."),
    ("Spell Scroll (Protection from Undead)", 1, "location", None, "Van Richten's Tower", None,
     "Inside Rictavio's carnival wagon outside the tower."),
    ("Spell Scroll (Major Image)", 1, "npc", "Ezmerelda d'Avenir", "Van Richten's Tower", None,
     "Stored inside Ezmerelda's wagon."),
    ("Spell Scroll (Remove Curse)", 1, "npc", "Ezmerelda d'Avenir", "Van Richten's Tower", None,
     "Stored inside Ezmerelda's wagon."),
    ("Khazan's Phylactery", 1, "location", None, "Van Richten's Tower", None,
     "Hidden in a secret compartment behind a suit of armour. Destructible only by a strike "
     "from the Staff of Power."),
    ("Flamboyant Vistani Wagon", 1, "npc", "Ezmerelda d'Avenir", "Van Richten's Tower", None,
     "Ezmerelda's wagon. If the party retrieves it, driving it grants a Fast pace (4 mph) with "
     "no penalty; can't be taken into the deep Barovian woods. Assumes she was met elsewhere and "
     "the wagon remains here intact — adjust if she's met at the tower instead."),

    # -- Location Unknown --
    ("Magic Gem (Lost)", 1, "unowned", None, None, None,
     "The third of the Winery's stolen gems. Its whereabouts are deliberately left a mystery per "
     "the Master Quest notes — a hook for a custom side-quest, placement left to the DM."),

    # -- The Amber Temple (Chapter 13) --
    ("Staff of Frost", 1, "location", None, "The Amber Temple", None, "Upper west hall (X17)."),
    ("Tome of Understanding", 1, "location", None, "The Amber Temple", None,
     "Architect's room (X20)."),
    ("Robe of Useful Items", 1, "location", None, "The Amber Temple", None,
     "Hall of hidden secrets (X5a)."),
    ("Wand of Secrets", 1, "location", None, "The Amber Temple", None, "Guard room (X2b)."),
]


def _entity_id(session, name: str, entity_type: str) -> str | None:
    entity = session.scalar(
        select(Entity).where(
            Entity.campaign_id == CAMPAIGN_ID,
            Entity.entity_type == entity_type,
            Entity.name == name,
            Entity.deleted_at_real.is_(None),
        )
    )
    return entity.id if entity else None


def main() -> None:
    with SessionLocal() as session:
        campaign = session.get(Campaign, CAMPAIGN_ID)
        if campaign is None:
            print(f"Error: campaign {CAMPAIGN_ID} not found.")
            sys.exit(1)

        added = library_seed_cos.ensure_seeded(session)
        print(f"Library: {added} new Curse of Strahd template(s) seeded.")

        catalog_new = items_new = 0
        for name, qty, holder_type, holder_name, loc_name, label, notes in PLACEMENTS:
            entry = session.scalar(
                select(LibraryEntry).where(
                    LibraryEntry.name == name,
                    LibraryEntry.source == library_seed_cos.SEED_SOURCE,
                )
            )
            if entry is None:
                print(f"  ! no 'cos' library entry named {name!r} — skipped.")
                continue

            existing = session.scalar(
                select(Equipment).where(
                    Equipment.campaign_id == CAMPAIGN_ID,
                    Equipment.library_id == entry.id,
                )
            )
            eq = equipment_service.import_from_library(
                session, campaign, ImportFromLibrary(library_id=entry.id), created_by=campaign.created_by
            )
            if existing is None:
                catalog_new += 1

            have = session.scalar(
                select(Item).where(Item.equipment_id == eq.entity_id)
            )
            if have is not None:
                print(f"  = {name}: copies already placed, left alone.")
                continue

            holder_id = None
            if holder_type == "npc":
                holder_id = _entity_id(session, holder_name, "npc")
                if holder_id is None:
                    print(f"  ! NPC {holder_name!r} not found — placing {name} at its location instead.")
                    holder_type = "location"
            location_id = _entity_id(session, loc_name, "location") if loc_name else None
            if loc_name and location_id is None:
                print(f"  ! location {loc_name!r} not found — {name} left unowned.")
                holder_type = "unowned"
            if holder_type == "location":
                holder_id = location_id

            for _ in range(qty):
                equipment_service.create_item(
                    session, campaign,
                    ItemInstanceCreate(
                        equipment_id=eq.entity_id,
                        instance_label=label,
                        notes=notes,
                        initial_holder_type=holder_type,
                        initial_holder_id=holder_id,
                        initial_location_id=location_id,
                    ),
                    created_by=campaign.created_by,
                )
                items_new += 1
            where = holder_name or loc_name or "unowned (Tarokka)"
            print(f"  + {name} x{qty} -> {where}")

        print(f"\nDone. {catalog_new} catalog definition(s) imported, {items_new} copies placed.")


if __name__ == "__main__":
    main()
