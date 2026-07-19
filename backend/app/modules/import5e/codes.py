"""Decode 5etools abbreviation codes into human strings.

Sizes, magic schools and damage types are small fixed tables. Item ``type``/``property``
codes are *not* hard-coded — 5etools ships the authoritative dictionaries inside
``items-base.json`` (`itemType`, `itemProperty`), so :func:`build_item_dicts` reads them
from whatever file the caller loaded.
"""

from __future__ import annotations

from typing import Any

# 5etools size codes -> our monster ``size`` enum (Tiny…Gargantuan).
SIZE = {
    "T": "Tiny", "S": "Small", "M": "Medium",
    "L": "Large", "H": "Huge", "G": "Gargantuan",
}

# Magic school codes -> full names.
SCHOOL = {
    "A": "Abjuration", "C": "Conjuration", "D": "Divination", "E": "Enchantment",
    "V": "Evocation", "I": "Illusion", "N": "Necromancy", "T": "Transmutation",
    "P": "Psionic",
}

# Damage type codes used in weapon ``dmgType``.
DAMAGE_TYPE = {
    "A": "acid", "B": "bludgeoning", "C": "cold", "F": "fire", "O": "force",
    "L": "lightning", "N": "necrotic", "P": "piercing", "I": "poison",
    "Y": "psychic", "R": "radiant", "S": "slashing", "T": "thunder",
}


def size_name(code: Any) -> str | None:
    """``["S"]`` or ``"S"`` -> ``"Small"``. Unknown/missing -> ``None``."""
    if isinstance(code, list):
        code = code[0] if code else None
    if not isinstance(code, str):
        return None
    return SIZE.get(code.upper())


def school_name(code: str | None) -> str | None:
    if not code:
        return None
    return SCHOOL.get(code.upper(), code)


def damage_type(code: str | None) -> str | None:
    if not code:
        return None
    return DAMAGE_TYPE.get(code.upper(), code)


def build_item_dicts(items_base: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build ``{"type": {abbr: name}, "property": {abbr: name}}`` from ``items-base.json``.

    ``itemType`` entries carry ``abbreviation`` + ``name``; ``itemProperty`` entries carry
    ``abbreviation`` and the display name inside a nested ``entries[0].name``.
    """
    type_map: dict[str, str] = {}
    for t in items_base.get("itemType", []):
        abbr = t.get("abbreviation")
        name = t.get("name")
        if abbr and name:
            type_map[abbr] = name
    prop_map: dict[str, str] = {}
    for p in items_base.get("itemProperty", []):
        abbr = p.get("abbreviation")
        if not abbr:
            continue
        name = None
        entries = p.get("entries")
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            name = entries[0].get("name")
        prop_map[abbr] = name or abbr
    return {"type": type_map, "property": prop_map}


def item_type_name(dicts: dict[str, dict[str, str]], code: Any | None) -> str | None:
    """Resolve a base-item ``type`` code (may be ``"M|XPHB"``) to its full name."""
    if not code or not isinstance(code, str):
        return None
    abbr = code.split("|", 1)[0].strip()
    return dicts.get("type", {}).get(abbr, abbr)


def property_names(
    dicts: dict[str, dict[str, str]], props: list[Any] | None
) -> list[str]:
    """Resolve a base-item ``property`` list (codes like ``"V"``, ``"F|XPHB"``) to names."""
    out: list[str] = []
    for code in props or []:
        if not isinstance(code, str):
            continue
        abbr = code.split("|", 1)[0].strip()
        out.append(dicts.get("property", {}).get(abbr, abbr))
    return out


#: XP awarded per challenge rating (DMG p.274). 5etools bestiary entries carry no ``xp``
#: field — XP is a pure function of CR — so this table is the only source. Without it every
#: imported monster scores 0 XP and ``encounter_difficulty()`` rates every fight "trivial".
XP_BY_CR: dict[float, int] = {
    0.0: 10, 0.125: 25, 0.25: 50, 0.5: 100,
    1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800, 6: 2300, 7: 2900, 8: 3900, 9: 5000,
    10: 5900, 11: 7200, 12: 8400, 13: 10000, 14: 11500, 15: 13000, 16: 15000,
    17: 18000, 18: 20000, 19: 22000, 20: 25000, 21: 33000, 22: 41000, 23: 50000,
    24: 62000, 25: 75000, 26: 90000, 27: 105000, 28: 120000, 29: 135000, 30: 155000,
}


def xp_for_cr(cr: float | None) -> int | None:
    """XP for a challenge rating, or ``None`` when the CR is unknown/off-table."""
    if cr is None:
        return None
    return XP_BY_CR.get(float(cr))


#: 5etools alignment codes. "A" is the catch-all for "any alignment"; "NX"/"NY" are the
#: lawful-chaotic and good-evil neutral axes, both of which print as "neutral".
_ALIGNMENT = {
    "L": "lawful", "C": "chaotic", "N": "neutral", "NX": "neutral", "NY": "neutral",
    "G": "good", "E": "evil", "U": "unaligned", "A": "any alignment",
}


def alignment_str(codes: Any | None) -> str | None:
    """``["C", "E"]`` -> ``"chaotic evil"``; ``["N"]`` -> ``"neutral"``."""
    if not isinstance(codes, list):
        return None
    words = [_ALIGNMENT[c] for c in codes if isinstance(c, str) and c in _ALIGNMENT]
    if not words:
        return None
    # ["N", "N"] would print "neutral neutral"; the SRD writes that as plain "neutral".
    if len(words) == 2 and words[0] == words[1] == "neutral":
        return "neutral"
    return " ".join(words)
