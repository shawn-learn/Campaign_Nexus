"""Add LegoLess to the Curse of Strahd party.

Imported from D&D Beyond character 100597937. As with BOB, the 5e PC schema is
combat-facing, so the sheet's flavour (race, background, kit) lands in ``notes``.
Attacks are stored as *ingredients* (ability + proficient + bare weapon die) so they
stay correct when LegoLess levels, rather than as baked-in literals.
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

NAME = "LegoLess"

DOC = {
    "class_name": "Fighter (Eldritch Knight)",
    "level": 4,
    "abilities": {"str": 16, "dex": 14, "con": 11, "int": 9, "wis": 8, "cha": 8},
    "max_hit_points": 28,
    "current_hit_points": 28,
    # Scale mail (14) + Dex (+2, medium-armour cap). The D&D Beyond summary read 14,
    # which is the armour's base with the Dex bonus dropped.
    "armor_class": 16,
    "proficient_saves": ["str", "con"],
    "spellcasting_ability": "int",
    "actions": [
        {
            "name": "Shortbow",
            "kind": "ranged",
            "ability": "dex",
            "proficient": True,
            "reach": "range 80/320 ft.",
            "target": "one target",
            "damage": [{"dice": "1d6", "type": "piercing", "add_ability": True}],
        },
    ],
    "notes": (
        "Wood Elf Fighter 4 (Eldritch Knight), Noble background. Imported from D&D "
        "Beyond character 100597937.\n\n"
        "Spellcasting: Intelligence, save DC 9, spell attack +1. Three 1st-level wizard "
        "spells known (two must be abjuration or evocation) — the individual spells were "
        "not in the imported data.\n\n"
        "Equipment: scale mail (worn; disadvantage on Stealth), leather armor, shortbow "
        "with 20 arrows, fine clothes, signet ring, scroll of pedigree, 25 gp.\n\n"
        "Proficiency bonus +2.\n\n"
        "Not captured by the import: Fighting Style, Second Wind, Action Surge, and the "
        "level-4 ASI. No melee weapon was listed on the sheet despite Str 16 — worth "
        "checking before combat."
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
