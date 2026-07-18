"""Convert 5etools item entries into equipment ``LibraryEntry`` fields.

Handles both ``items-base.json`` base items (mundane gear/weapons/armor) and ``items.json``
magic items. Output keys match ``LibraryEntryCreate``: ``name, summary, item_type, rarity,
requires_attunement, value_gp, weight_lb, properties, source``.
"""

from __future__ import annotations

from typing import Any, Optional

from app.modules.import5e import codes, tags

# 5etools rarity string -> our enum (common|uncommon|rare|very_rare|legendary) or None.
_RARITY = {
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "very rare": "very_rare",
    "legendary": "legendary",
    "artifact": "legendary",  # our enum tops out at legendary
}
# Rarities that, on their own, don't make an item "magical".
_MUNDANE_RARITY = {None, "none", "unknown", "varies"}


def money_str(value_cp: Any) -> Optional[str]:
    """Copper-piece value -> a display string in the largest tidy unit. ``1500`` -> ``"15 gp"``."""
    if not isinstance(value_cp, (int, float)) or value_cp <= 0:
        return None
    cp = int(value_cp)
    if cp % 100 == 0:
        return f"{cp // 100} gp"
    if cp >= 100:
        return f"{cp / 100:g} gp"
    if cp % 10 == 0:
        return f"{cp // 10} sp"
    return f"{cp} cp"


def _rarity(entry: dict[str, Any]) -> Optional[str]:
    return _RARITY.get((entry.get("rarity") or "").lower())


def _is_magical(entry: dict[str, Any]) -> bool:
    rarity = (entry.get("rarity") or "").lower() or None
    if rarity not in _MUNDANE_RARITY:
        return True
    return bool(entry.get("wondrous") or entry.get("reqAttune") or entry.get("staff"))


def _base_item_properties(
    entry: dict[str, Any], item_dicts: dict[str, dict[str, str]]
) -> str:
    """A one-line summary for a mundane base item: category, damage, properties."""
    bits: list[str] = []
    type_name = codes.item_type_name(item_dicts, entry.get("type"))
    category = entry.get("weaponCategory")
    if category and type_name:
        bits.append(f"{category.capitalize()} {type_name.lower()}")
    elif type_name:
        bits.append(type_name)
    dmg1 = entry.get("dmg1")
    if dmg1:
        dtype = codes.damage_type(entry.get("dmgType")) or ""
        bits.append(f"{dmg1} {dtype}".strip())
    props = codes.property_names(item_dicts, entry.get("property"))
    if props:
        detail = ", ".join(props).lower()
        dmg2 = entry.get("dmg2")
        if dmg2:
            detail += f" ({dmg2})"
        bits.append(detail)
    return "; ".join(bits)


def _magic_item_properties(entry: dict[str, Any]) -> str:
    """Flatten a magic item's ``entries`` into plain text (tags stripped)."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            name = node.get("name")
            if name:
                parts.append(f"{name}.")
            for key in ("entries", "items"):
                if key in node:
                    walk(node[key])

    walk(entry.get("entries"))
    return tags.strip_tags(" ".join(p for p in parts if p))


def to_library_entry(
    entry: dict[str, Any],
    item_dicts: dict[str, dict[str, str]],
    *,
    source: str,
    is_base: bool = False,
) -> Optional[dict[str, Any]]:
    """Reshape a 5etools item into ``LibraryEntry`` fields, or ``None`` to skip it."""
    name = entry.get("name")
    if not name:
        return None

    magical = False if is_base else _is_magical(entry)
    if is_base:
        properties = _base_item_properties(entry, item_dicts)
    else:
        properties = _magic_item_properties(entry)

    weight = entry.get("weight")
    return {
        "name": name,
        "summary": (properties[:140] or None) if properties else None,
        "item_type": "magical" if magical else "mundane",
        "rarity": _rarity(entry),
        "requires_attunement": bool(entry.get("reqAttune")),
        "value_gp": money_str(entry.get("value")),
        "weight_lb": float(weight) if isinstance(weight, (int, float)) else None,
        "properties": properties,
        "source": source,
    }
