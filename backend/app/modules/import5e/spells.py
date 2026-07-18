"""Convert a 5etools spell entry into Campaign_Nexus spell-catalog fields.

Output keys match the ``SpellCreate`` schema (see ``app.modules.spells``). Class lists are
not on the spell in 5etools — they live in ``spells/sources.json`` — so the caller passes
the resolved class names in via ``classes``.
"""

from __future__ import annotations

from typing import Any, Optional

from app.modules.import5e import codes, tags


def _flatten(node: Any, parts: list[str]) -> None:
    if isinstance(node, str):
        parts.append(node)
    elif isinstance(node, list):
        for item in node:
            _flatten(item, parts)
    elif isinstance(node, dict):
        name = node.get("name")
        if name:
            parts.append(f"{name}.")
        for key in ("entries", "items"):
            if key in node:
                _flatten(node[key], parts)


def _text(node: Any) -> str:
    parts: list[str] = []
    _flatten(node, parts)
    return tags.strip_tags(" ".join(p for p in parts if p))


def casting_time(time: Any) -> Optional[str]:
    if not isinstance(time, list) or not time:
        return None
    t = time[0]
    if not isinstance(t, dict):
        return None
    num = t.get("number")
    unit = t.get("unit", "")
    label = f"{num} {unit}".strip()
    if num == 1 or num is None:
        label = label  # keep singular/plural simple; 5etools units read fine either way
    cond = t.get("condition")
    return f"{label}, {cond}" if cond else label


def range_text(rng: Any) -> Optional[str]:
    if not isinstance(rng, dict):
        return None
    rtype = rng.get("type")
    dist = rng.get("distance")
    if rtype in ("self", "touch") and not isinstance(dist, dict):
        return rtype.capitalize()
    if isinstance(dist, dict):
        dt = dist.get("type")
        amount = dist.get("amount")
        if dt == "self":
            base = "Self"
        elif dt == "touch":
            base = "Touch"
        elif dt in ("sight", "unlimited"):
            base = dt.capitalize()
        elif amount is not None:
            base = f"{amount} {dt}"
        else:
            base = (dt or "").capitalize()
        # Shape it: a 20-foot-radius area etc.
        if rtype in ("radius", "sphere", "cone", "line", "cube", "hemisphere"):
            return f"Self ({base} {rtype})"
        return base
    return (rtype or "").capitalize() or None


def duration_text(duration: Any) -> tuple[Optional[str], bool]:
    """Return ``(text, concentration)``."""
    if not isinstance(duration, list) or not duration:
        return None, False
    d = duration[0]
    if not isinstance(d, dict):
        return None, False
    concentration = bool(d.get("concentration"))
    dtype = d.get("type")
    if dtype == "instant":
        text = "Instantaneous"
    elif dtype == "permanent":
        text = "Until dispelled"
    elif dtype == "special":
        text = "Special"
    elif dtype == "timed":
        inner = d.get("duration", {})
        amount = inner.get("amount")
        unit = inner.get("type", "")
        text = f"{amount} {unit}".strip()
    else:
        text = (dtype or "").capitalize() or None
    if concentration and text:
        text = f"Concentration, up to {text}"
    return text, concentration


def _components(comp: Any) -> tuple[bool, bool, bool, Optional[str]]:
    """Return ``(v, s, m, material_text)``."""
    if not isinstance(comp, dict):
        return False, False, False, None
    m = comp.get("m")
    material: Optional[str] = None
    if isinstance(m, str):
        material = m
    elif isinstance(m, dict):
        material = m.get("text")
    return bool(comp.get("v")), bool(comp.get("s")), bool(m), material


def to_spell(
    entry: dict[str, Any], *, classes: Optional[list[str]] = None
) -> Optional[dict[str, Any]]:
    """Reshape one 5etools ``spell`` entry into ``SpellCreate`` fields, or ``None`` to skip."""
    name = entry.get("name")
    level = entry.get("level")
    if not name or not isinstance(level, int):
        return None

    v, s, m, material = _components(entry.get("components"))
    duration, concentration = duration_text(entry.get("duration"))
    meta = entry.get("meta") or {}
    damage = entry.get("damageInflict") or []
    saves = entry.get("savingThrow") or []

    return {
        "name": name,
        "source": entry.get("source") or "",
        "level": level,
        "school": codes.school_name(entry.get("school")),
        "casting_time": casting_time(entry.get("time")),
        "range_text": range_text(entry.get("range")),
        "component_v": v,
        "component_s": s,
        "component_m": m,
        "material": material,
        "concentration": concentration,
        "ritual": bool(meta.get("ritual")),
        "classes": ", ".join(classes) if classes else None,
        "duration": duration,
        "description": _text(entry.get("entries")),
        "higher_levels": _text(entry.get("entriesHigherLevel")) or None,
        "damage_types": ", ".join(damage) if damage else None,
        "saving_throw": ", ".join(saves) if saves else None,
    }


def load_class_map(sources: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    """Invert ``spells/sources.json`` into ``{(spell_name, source): [class names]}``.

    Shape: ``{ SOURCE: { "Spell Name": { "class": [{"name": "Wizard", ...}], ... } } }``.
    """
    out: dict[tuple[str, str], list[str]] = {}
    for src, spells in sources.items():
        if not isinstance(spells, dict):
            continue
        for spell_name, avail in spells.items():
            names: list[str] = []
            for cls in (avail.get("class") or []) if isinstance(avail, dict) else []:
                cname = cls.get("name") if isinstance(cls, dict) else None
                if cname:
                    names.append(cname)
            if names:
                out[(spell_name, src)] = sorted(set(names))
    return out
