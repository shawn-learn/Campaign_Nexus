"""Add Susaergal Calbackle to the Curse of Strahd party.

Imported from D&D Beyond character 95993317.

  * AC 15 = Draconic Resilience unarmored (13 + Dex +2). The import returned the
    formula unresolved ("13 + DEX modifier") rather than a number.
  * HP 19 = the sheet's 16 plus the +3 from Draconic Resilience (+1 per sorcerer
    level), which the sheet appears not to have applied — 16 is below the arithmetic
    minimum of 17 for this build. Confirmed with the GM.
  * The import reported spell save DC 13, which contradicts its own spell attack of
    +4; both derive from Cha +2, so the DC is 12. The engine derives this itself.
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

NAME = "Susaergal Calbackle"

DOC = {
    "class_name": "Sorcerer (Draconic Bloodline)",
    "level": 3,
    "abilities": {"str": 11, "dex": 14, "con": 14, "int": 11, "wis": 7, "cha": 15},
    "max_hit_points": 19,
    "current_hit_points": 19,
    # Draconic Resilience: unarmored AC is 13 + Dex.
    "armor_class": 15,
    "proficient_saves": ["con", "cha"],
    "spellcasting_ability": "cha",
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
    ],
    "notes": (
        "Rock Gnome Sorcerer 3 (Draconic Bloodline), Noble background. Player: Greg. "
        "Imported from D&D Beyond character 95993317.\n\n"
        "Sheet name is 'Susaergal TBD Calbackle' — the middle name is still a "
        "placeholder on the sheet.\n\n"
        "AC 15 = Draconic Resilience unarmored (13 + Dex +2); wears no armor.\n"
        "HP 19 = the sheet's 16 plus the +3 from Draconic Resilience that it had not "
        "applied (16 is below the minimum possible 17 for this build).\n"
        "Spellcasting: Charisma, save DC 12, spell attack +4. 2 sorcery points at level 3.\n\n"
        "Draconic Bloodline: Dragon Ancestor (draconic language, doubled proficiency on "
        "Charisma checks with dragons), Draconic Resilience. Also Font of Magic and two "
        "Metamagic options.\n"
        "Rock Gnome: Gnome Cunning (advantage on Int/Wis/Cha saves vs magic), Artificer's "
        "Lore, Tinker. Noble background: Position of Privilege.\n\n"
        "Equipment: common clothes, dagger, signet ring, scroll of pedigree, 25 gp.\n\n"
        "NOT captured by the import: the specific spells and cantrips (a level-3 Sorcerer "
        "knows 4 spells and 4 cantrips), the chosen dragon ancestry and its damage type, "
        "and the two Metamagic options. All are worth filling in from the sheet."
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
