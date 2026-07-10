"""SRD 5.1 content pack (subset). Content under CC-BY-4.0; attribution rendered in-app."""

from __future__ import annotations

from typing import Any

ATTRIBUTION = (
    "This work includes material from the System Reference Document 5.1 by Wizards of the "
    "Coast LLC, available under the Creative Commons Attribution 4.0 International License."
)


def _m(
    name: str, size: str, mtype: str, ac: int, hp: int, cr: float, xp: int, ab: dict[str, int]
) -> dict[str, Any]:
    return {
        "name": name,
        "doc": {
            "size": size, "type": mtype, "armor_class": ac, "hit_points": hp,
            "challenge_rating": cr, "xp": xp, "abilities": ab,
        },
    }


_SRD_MONSTERS: list[dict[str, Any]] = [
    _m("Goblin", "Small", "humanoid", 15, 7, 0.25, 50,
       {"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8}),
    _m("Bugbear", "Medium", "humanoid", 16, 27, 1, 200,
       {"str": 15, "dex": 14, "con": 13, "int": 8, "wis": 11, "cha": 9}),
    _m("Brown Bear", "Large", "beast", 11, 34, 1, 200,
       {"str": 19, "dex": 10, "con": 16, "int": 2, "wis": 13, "cha": 7}),
    _m("Ogre", "Large", "giant", 11, 59, 2, 450,
       {"str": 19, "dex": 8, "con": 16, "int": 5, "wis": 7, "cha": 7}),
    _m("Griffon", "Large", "monstrosity", 12, 59, 2, 450,
       {"str": 18, "dex": 15, "con": 16, "int": 2, "wis": 13, "cha": 8}),
    _m("Wight", "Medium", "undead", 14, 45, 3, 700,
       {"str": 15, "dex": 14, "con": 16, "int": 10, "wis": 13, "cha": 15}),
    _m("Mummy", "Medium", "undead", 11, 58, 3, 700,
       {"str": 16, "dex": 8, "con": 15, "int": 6, "wis": 10, "cha": 12}),
    _m("Owlbear", "Large", "monstrosity", 13, 59, 3, 700,
       {"str": 20, "dex": 12, "con": 17, "int": 3, "wis": 12, "cha": 7}),
    _m("Ghost", "Medium", "undead", 11, 45, 4, 1100,
       {"str": 7, "dex": 13, "con": 10, "int": 10, "wis": 12, "cha": 17}),
    _m("Wraith", "Medium", "undead", 13, 67, 5, 1800,
       {"str": 6, "dex": 16, "con": 16, "int": 12, "wis": 14, "cha": 15}),
    _m("Vampire Spawn", "Medium", "undead", 15, 82, 5, 1800,
       {"str": 16, "dex": 16, "con": 16, "int": 11, "wis": 10, "cha": 12}),
    _m("Xorn", "Medium", "elemental", 19, 73, 5, 1800,
       {"str": 17, "dex": 10, "con": 22, "int": 11, "wis": 10, "cha": 11}),
]

CONTENT_PACK: dict[str, Any] = {
    "id": "srd51",
    "version": "5.1",
    "attribution": ATTRIBUTION,
    "monsters": _SRD_MONSTERS,
}
