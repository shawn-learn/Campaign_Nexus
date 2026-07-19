"""Add Lloyd Skullcrusher to the Curse of Strahd party.

Imported from D&D Beyond character 95992966. The source fetch for this one was badly
degraded (the summariser looped and miscalculated both AC and HP), so the numbers here
were reconciled by hand against 5e arithmetic and confirmed with the GM:

  * AC 17 = Unarmored Defense (10 + Dex 2 + Con 3) + shield 2. The import reported 13,
    which did not match its own stated formula.
  * HP 36 is a rolled total, confirmed by the GM — the level-4 average would be 45.

Rage bonus damage (+2) is deliberately NOT baked into the attacks below, since it only
applies while raging and to melee Strength attacks; it lives in ``notes`` instead.
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

NAME = "Lloyd Skullcrusher"

DOC = {
    "class_name": "Barbarian (Path of the Giant)",
    "level": 4,
    "abilities": {"str": 17, "dex": 14, "con": 16, "int": 12, "wis": 14, "cha": 14},
    "max_hit_points": 36,
    "current_hit_points": 36,
    # Unarmored Defense (10 + Dex + Con) + shield. Barbarian UD explicitly allows a shield.
    "armor_class": 17,
    "proficient_saves": ["str", "con"],
    "actions": [
        {
            "name": "Greataxe",
            "kind": "melee",
            "ability": "str",
            "proficient": True,
            "reach": "5 ft.",
            "target": "one target",
            "damage": [{"dice": "1d12", "type": "slashing", "add_ability": True}],
            "description": "Equipped. Reach becomes 10 ft. while raging (Giant's Havoc).",
        },
        {
            "name": "Battleaxe",
            "kind": "melee",
            "ability": "str",
            "proficient": True,
            "reach": "5 ft.",
            "target": "one target",
            "damage": [{"dice": "1d8", "type": "slashing", "add_ability": True}],
            "description": "Versatile: 1d10 when wielded two-handed.",
        },
        {
            "name": "Shortsword",
            "kind": "melee",
            "ability": "dex",  # finesse
            "proficient": True,
            "reach": "5 ft.",
            "target": "one target",
            "damage": [{"dice": "1d6", "type": "piercing", "add_ability": True}],
        },
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
            "description": "Crushing Throw adds Rage damage to thrown weapon attacks.",
        },
        {
            "name": "Sling",
            "kind": "ranged",
            "ability": "dex",
            "proficient": True,
            "reach": "range 30/120 ft.",
            "target": "one target",
            "damage": [{"dice": "1d4", "type": "bludgeoning", "add_ability": True}],
        },
    ],
    "notes": (
        "Human Barbarian 4 (Path of the Giant), Soldier background. Neutral, male, age 24. "
        "Imported from D&D Beyond character 95992966.\n\n"
        "AC 17 = Unarmored Defense (10 + Dex +2 + Con +3) + shield +2.\n"
        "HP 36 is a rolled total (the level-4 average would be 45).\n\n"
        "Rage: 4 per long rest, +2 bonus damage on melee Strength attacks (and on thrown "
        "weapons via Crushing Throw). While raging: advantage on Strength checks and saves, "
        "resistance to bludgeoning/piercing/slashing.\n"
        "Giant's Havoc (while raging): reach +5 ft., size becomes Large.\n"
        "Also: Reckless Attack, Danger Sense, Giant's Power (Giant language + a cantrip, "
        "cantrip not yet chosen on the sheet).\n\n"
        "Skills: Athletics, Intimidation. Tools: gaming set, vehicles (land). "
        "Proficiency bonus +2. Speed 30 ft.\n\n"
        "Equipment: greataxe (equipped), shield (equipped), battleaxe, shortsword, "
        "2 daggers, sling, insignia of rank, bone dice, common clothes. No coin recorded, "
        "no magic items, no attunements.\n\n"
        "Backstory: second son of a northern-mountain barbarian clan leader, separated from "
        "the clan after rivalry with his older brother. Allied with stone giants. Adds a "
        "small white skull tattoo for each enemy killed.\n\n"
        "CAVEAT: the D&D Beyond import for this character was unreliable — it miscalculated "
        "both AC and HP, and its account of the level-4 ASI was incoherent (it described the "
        "Standard Human +1-to-all racial as the ASI). Str 17 suggests the level-4 ASI may "
        "not have been applied. Worth checking the ability scores against the live sheet."
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
