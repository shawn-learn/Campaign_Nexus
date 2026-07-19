"""Add Coy to the Curse of Strahd party.

Imported from D&D Beyond character 100805118.

  * AC 12 = leather (11) + Dex (+1). The import reported 11, the armour's base value
    with the Dex bonus dropped — the same error seen on the other three imports.
  * HP 23 is taken as reported; it sits above the level-3 average of 21, consistent
    with a good roll rather than a miscalculation.

The scimitar is stored using Hex Warrior (Charisma) rather than its finesse Dexterity,
since that is the defining Hexblade feature and Coy has no other reason to carry a
martial weapon at Str 9 / Dex 13. See the note below if the weapon is not bonded.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is in search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import SessionLocal
from app.modules.playbook.service import add_member
from app.modules.rules.service import create_stat_block

CAMPAIGN_ID = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd

NAME = "Coy"

DOC = {
    "class_name": "Warlock (Hexblade)",
    "level": 3,
    "abilities": {"str": 9, "dex": 13, "con": 13, "int": 11, "wis": 13, "cha": 15},
    "max_hit_points": 23,
    "current_hit_points": 23,
    # Leather (11) + Dex (+1). The import reported 11, dropping the Dex bonus.
    "armor_class": 12,
    "proficient_saves": ["wis", "cha"],
    "spellcasting_ability": "cha",
    "actions": [
        {
            "name": "Scimitar",
            "kind": "melee",
            "ability": "cha",  # Hex Warrior; would be dex (finesse) if not bonded
            "proficient": True,
            "reach": "5 ft.",
            "target": "one target",
            "damage": [{"dice": "1d6", "type": "slashing", "add_ability": True}],
            "description": (
                "Bonded via Hex Warrior, so attack and damage use Charisma. If the bond "
                "is not active, this reverts to Dexterity (finesse) for +1 instead of +2."
            ),
        },
    ],
    "notes": (
        "Human Warlock 3 (Hexblade), Soldier background. Imported from D&D Beyond "
        "character 100805118.\n\n"
        "AC 12 = leather armor (11) + Dex (+1).\n"
        "HP 23 (level-3 average is 21 — taken as a good roll).\n"
        "Spellcasting: Charisma, save DC 12, spell attack +4. Warlock slots at level 3: "
        "2 slots, both 2nd level, recovered on a short rest.\n\n"
        "Hexblade: Hex Warrior (bond a one-handed melee weapon, use Cha for its attack and "
        "damage), Hexblade's Curse, plus proficiency with medium armor, shields and martial "
        "weapons.\n\n"
        "Equipment: leather armor, scimitar, common clothes, component pouch or arcane "
        "focus. No shield.\n\n"
        "NOT captured by the import: the specific spells and cantrips (a level-3 Warlock "
        "knows 4 spells and 2 cantrips; the import mentioned only 'two 1st-level spells, "
        "not specified'), the Pact Boon choice (Blade / Chain / Tome), and the two Eldritch "
        "Invocations. All three matter in play and are worth filling in from the sheet."
    ),
}


def main() -> None:
    session = SessionLocal()
    try:
        block = create_stat_block(
            session,
            CAMPAIGN_ID,
            rule_system_id="dnd5e",
            sheet_type="pc",
            label=NAME,
            doc=DOC,
        )
        print(f"Created stat block {block['id']} ({NAME})")
        add_member(session, CAMPAIGN_ID, block["id"], None)
        print(f"Added {NAME} to the Curse of Strahd party")
    finally:
        session.close()


if __name__ == "__main__":
    main()
