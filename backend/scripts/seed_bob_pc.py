"""Add BOB (Ryan's character) to the Curse of Strahd party.

Imported from D&D Beyond character 95987147. The 5e PC schema is combat-facing, so
the sheet's flavour (race, background, kit) lands in ``notes`` rather than in fields
of its own. Attacks are stored as *ingredients* (ability + proficient + bare weapon
die) so they stay correct when BOB levels, rather than as baked-in literals.
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

NAME = "BOB"

DOC = {
    "class_name": "Rogue (Arcane Trickster)",
    "level": 3,
    "abilities": {"str": 10, "dex": 15, "con": 13, "int": 13, "wis": 11, "cha": 6},
    "max_hit_points": 20,
    "current_hit_points": 20,
    # Leather (11) + Dex (+2). The D&D Beyond summary read 12; 13 is the computed value.
    "armor_class": 13,
    "proficient_saves": ["dex", "int"],
    "spellcasting_ability": "int",
    "actions": [
        {
            "name": "Dagger",
            "kind": "melee",
            "ability": "dex",  # finesse
            "proficient": True,
            "reach": "5 ft.",
            "target": "one target",
            "damage": [{"dice": "1d4", "type": "piercing", "add_ability": True}],
        },
        {
            "name": "Dagger (thrown)",
            "kind": "ranged",
            "ability": "dex",
            "proficient": True,
            "reach": "range 20/60 ft.",
            "target": "one target",
            "damage": [{"dice": "1d4", "type": "piercing", "add_ability": True}],
        },
        {
            "name": "Sneak Attack",
            "description": (
                "Once per turn, +1d6 damage on a hit with a finesse or ranged weapon if "
                "you have advantage, or if an ally is within 5 ft. of the target and you "
                "do not have disadvantage."
            ),
            "damage": [{"dice": "1d6"}],
        },
    ],
    "notes": (
        "Human Rogue 3 (Arcane Trickster). Ryan's character. Imported from D&D Beyond "
        "character 95987147.\n\n"
        "Spellcasting: Intelligence, save DC 11, spell attack +3. 3 cantrips known "
        "(includes Mage Hand), 3 first-level spells known (two from enchantment or "
        "illusion), 2 first-level slots.\n\n"
        "Equipment: leather armor (worn), 2 daggers, thieves' tools, magnifying glass, "
        "evidence from a past case, common clothes.\n\n"
        "XP: 900. Proficiency bonus +2."
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
