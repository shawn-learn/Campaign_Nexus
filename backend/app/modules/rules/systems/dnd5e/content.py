"""SRD 5.1 content pack (subset). Content under CC-BY-4.0; attribution rendered in-app."""

from __future__ import annotations

from typing import Any

ATTRIBUTION = (
    "This work includes material from the System Reference Document 5.1 by Wizards of the "
    "Coast LLC, available under the Creative Commons Attribution 4.0 International License."
)


def _atk(
    name: str,
    to_hit: int,
    dice: str,
    dtype: str,
    *,
    kind: str = "melee",
    reach: str = "5 ft.",
    target: str = "one target",
    extra: list[dict[str, str]] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """One printed attack line: "+4 to hit, reach 5 ft., one target. Hit: 1d6+2 slashing."

    Monsters store their numbers literally, exactly as the SRD prints them — they don't
    level, so there is nothing for the plugin to re-derive. (A PC's attack can instead name
    an ability and a proficiency; see ``_ATTACK_SCHEMA``.)
    """
    damage = [{"dice": dice, "type": dtype}, *(extra or [])]
    action: dict[str, Any] = {
        "name": name, "kind": kind, "to_hit": to_hit,
        "reach": reach, "target": target, "damage": damage,
    }
    if description:
        action["description"] = description
    return action


def _m(
    name: str, size: str, mtype: str, ac: int, hp: int, cr: float, xp: int, ab: dict[str, int],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "size": size, "type": mtype, "armor_class": ac, "hit_points": hp,
        "challenge_rating": cr, "xp": xp, "abilities": ab,
    }
    if actions:
        doc["actions"] = actions
    return {"name": name, "doc": doc}


_SRD_MONSTERS: list[dict[str, Any]] = [
    _m("Goblin", "Small", "humanoid", 15, 7, 0.25, 50,
       {"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8},
       [_atk("Scimitar", 4, "1d6+2", "slashing"),
        _atk("Shortbow", 4, "1d6+2", "piercing", kind="ranged",
             reach="range 80/320 ft.")]),
    _m("Bugbear", "Medium", "humanoid", 16, 27, 1, 200,
       {"str": 15, "dex": 14, "con": 13, "int": 8, "wis": 11, "cha": 9},
       [_atk("Morningstar", 4, "2d8+2", "piercing"),
        _atk("Javelin", 4, "2d6+2", "piercing", reach="reach 5 ft. or range 30/120 ft.")]),
    _m("Brown Bear", "Large", "beast", 11, 34, 1, 200,
       {"str": 19, "dex": 10, "con": 16, "int": 2, "wis": 13, "cha": 7},
       [_atk("Bite", 5, "1d8+4", "piercing"),
        _atk("Claws", 5, "2d6+4", "slashing")]),
    _m("Ogre", "Large", "giant", 11, 59, 2, 450,
       {"str": 19, "dex": 8, "con": 16, "int": 5, "wis": 7, "cha": 7},
       [_atk("Greatclub", 6, "2d8+4", "bludgeoning"),
        _atk("Javelin", 6, "2d6+4", "piercing", reach="reach 5 ft. or range 30/120 ft.")]),
    _m("Griffon", "Large", "monstrosity", 12, 59, 2, 450,
       {"str": 18, "dex": 15, "con": 16, "int": 2, "wis": 13, "cha": 8},
       [_atk("Beak", 6, "1d8+4", "piercing"),
        _atk("Claws", 6, "2d6+4", "slashing")]),
    _m("Wight", "Medium", "undead", 14, 45, 3, 700,
       {"str": 15, "dex": 14, "con": 16, "int": 10, "wis": 13, "cha": 15},
       [_atk("Longsword", 4, "1d8+2", "slashing",
             description="1d10+2 if wielded in two hands."),
        _atk("Longbow", 4, "1d8+2", "piercing", kind="ranged",
             reach="range 150/600 ft."),
        _atk("Life Drain", 4, "1d6+2", "necrotic",
             description="CON save DC 13 or hit point maximum is reduced by the damage "
                         "taken; a humanoid slain this way rises as a zombie.")]),
    _m("Mummy", "Medium", "undead", 11, 58, 3, 700,
       {"str": 16, "dex": 8, "con": 15, "int": 6, "wis": 10, "cha": 12},
       [_atk("Rotting Fist", 5, "2d6+3", "bludgeoning",
             extra=[{"dice": "3d6", "type": "necrotic"}],
             description="CON save DC 12 or be cursed with mummy rot.")]),
    _m("Owlbear", "Large", "monstrosity", 13, 59, 3, 700,
       {"str": 20, "dex": 12, "con": 17, "int": 3, "wis": 12, "cha": 7},
       [_atk("Beak", 7, "1d10+5", "piercing"),
        _atk("Claws", 7, "2d8+5", "slashing")]),
    _m("Ghost", "Medium", "undead", 11, 45, 4, 1100,
       {"str": 7, "dex": 13, "con": 10, "int": 10, "wis": 12, "cha": 17},
       [_atk("Withering Touch", 5, "4d6+3", "necrotic"),
        _atk("Horrifying Visage", 0, "0", "", kind="save",
             reach="60 ft.", target="each creature that can see it",
             description="WIS save DC 13 or be frightened for 1 minute; on a failure by 5 "
                         "or more, the target also ages 1d4 x 10 years.")]),
    _m("Wraith", "Medium", "undead", 13, 67, 5, 1800,
       {"str": 6, "dex": 16, "con": 16, "int": 12, "wis": 14, "cha": 15},
       [_atk("Life Drain", 6, "4d8+3", "necrotic",
             description="CON save DC 14 or hit point maximum is reduced by the damage "
                         "taken.")]),
    _m("Vampire Spawn", "Medium", "undead", 15, 82, 5, 1800,
       {"str": 16, "dex": 16, "con": 16, "int": 11, "wis": 10, "cha": 12},
       [_atk("Claws", 6, "2d4+3", "slashing",
             description="Instead of damage, can grapple (escape DC 13)."),
        _atk("Bite", 6, "1d6+3", "piercing",
             extra=[{"dice": "2d6", "type": "necrotic"}],
             target="one willing, grappled, incapacitated or restrained creature",
             description="The target's hit point maximum is reduced by the necrotic damage "
                         "and the vampire regains that many hit points.")]),
    _m("Xorn", "Medium", "elemental", 19, 73, 5, 1800,
       {"str": 17, "dex": 10, "con": 22, "int": 11, "wis": 10, "cha": 11},
       [_atk("Claw", 6, "1d6+3", "slashing"),
        _atk("Bite", 6, "3d6+3", "piercing"),
        _atk("Multiattack", 6, "1d6+3", "slashing",
             description="Three claw attacks and one bite attack.")]),
]

CONTENT_PACK: dict[str, Any] = {
    "id": "srd51",
    # 5.1 is the SRD's version; the suffix is this pack's. Bumping it refreshes the monsters
    # already imported into a campaign (see bestiary.import_content_packs) rather than
    # cloning them — which is how these attacks reach a bestiary seeded before they existed.
    "version": "5.1.1",
    "attribution": ATTRIBUTION,
    "monsters": _SRD_MONSTERS,
}
