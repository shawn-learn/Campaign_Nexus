"""Resolve 5etools ``_copy`` monster entries into standalone entries.

5etools stores variants as deltas against a base creature::

    {"name": "Barovian Commoner", "source": "CoS",
     "_copy": {"name": "Commoner", "source": "MM"},
     "action": [{"name": "Pitchfork", ...}]}

Everything the variant does not restate (``size``, ``ac``, ``hp``, ability scores…) lives on
the base. A converter reading the raw entry therefore sees almost nothing — which is why
``to_monster_doc`` skipped ~96% of ``_copy`` entries, including 79 of the 97 Curse of Strahd
creatures.

``resolve_copy`` merges the base in and applies the ``_copy._mod`` edit operations, so the
rest of the import layer can treat every entry as if it were authored in full.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Optional

#: 5etools bookkeeping that carries no game data. Dropped after resolution so the converted
#: doc stays clean and the ``additionalProperties: False`` monster schema is easier to satisfy.
_NOISE_KEYS = frozenset({
    "_copy", "_mod", "_versions", "_template", "_preserve",
    "altArt", "attachedItems", "basicRules", "environment", "familiar", "group",
    "hasFluff", "hasFluffImages", "hasToken", "reprintedAs", "soundClip",
    "actionTags", "conditionInflict", "conditionInflictLegendary", "conditionInflictSpell",
    "damageTags", "damageTagsLegendary", "damageTagsSpell", "languageTags", "miscTags",
    "savingThrowForced", "savingThrowForcedLegendary", "savingThrowForcedSpell",
    "senseTags", "spellcastingTags", "traitTags",
})

#: Keys a ``replaceTxt`` with target ``"*"`` must not rewrite — the variant's own identity.
_TEXT_SKIP_KEYS = frozenset({"name", "source", "page", "_copy"})

MonsterIndex = dict[tuple[str, str], dict[str, Any]]


def index_key(name: str, source: str) -> tuple[str, str]:
    return (name.strip().lower(), source.strip().lower())


def build_index(entries: Iterable[dict[str, Any]]) -> MonsterIndex:
    """Index raw bestiary entries by ``(name, source)`` for ``_copy`` base lookup.

    Must be built across *every* ``bestiary-*.json``: a variant routinely copies a base from
    a different source file (CoS creatures copy from MM).
    """
    index: MonsterIndex = {}
    for entry in entries:
        name, source = entry.get("name"), entry.get("source")
        if isinstance(name, str) and isinstance(source, str):
            index[index_key(name, source)] = entry
    return index


# --------------------------------------------------------------------------- #
# _mod operations
# --------------------------------------------------------------------------- #
def _as_list(value: Any) -> list[Any]:
    """``_mod`` payloads accept a bare object or a list of them; normalise to a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _walk_strings(node: Any, fn: Any) -> Any:
    """Rebuild ``node`` with every string passed through ``fn``."""
    if isinstance(node, str):
        return fn(node)
    if isinstance(node, list):
        return [_walk_strings(item, fn) for item in node]
    if isinstance(node, dict):
        return {key: _walk_strings(val, fn) for key, val in node.items()}
    return node


def _replace_txt(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    """Regex-replace text. 5etools builds a ``RegExp`` from ``replace``/``flags``."""
    pattern, replacement = op.get("replace"), op.get("with", "")
    if not isinstance(pattern, str):
        return
    flags = re.IGNORECASE if "i" in str(op.get("flags") or "") else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        regex = re.compile(re.escape(pattern), flags)

    def sub(text: str) -> str:
        return regex.sub(replacement, text)

    keys = entry.keys() if target in ("*", "_") else [target]
    for key in list(keys):
        if target in ("*", "_") and key in _TEXT_SKIP_KEYS:
            continue
        if key in entry:
            entry[key] = _walk_strings(entry[key], sub)


def _matches_name(item: Any, names: set[str]) -> bool:
    return isinstance(item, dict) and str(item.get("name", "")).lower() in names


def _replace_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    arr = entry.get(target)
    if not isinstance(arr, list):
        return
    replace, items = op.get("replace"), _as_list(op.get("items"))
    index: Optional[int] = None
    if isinstance(replace, dict) and isinstance(replace.get("index"), int):
        index = replace["index"]
    elif isinstance(replace, str):
        wanted = {replace.lower()}
        index = next((i for i, it in enumerate(arr) if _matches_name(it, wanted)), None)
    if index is None or not 0 <= index < len(arr):
        return
    entry[target] = arr[:index] + items + arr[index + 1:]


def _remove_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    arr = entry.get(target)
    if not isinstance(arr, list):
        return
    names = {str(n).lower() for n in _as_list(op.get("names")) if isinstance(n, str)}
    if names:
        entry[target] = [it for it in arr if not _matches_name(it, names)]
        return
    drop = _as_list(op.get("items"))
    entry[target] = [it for it in arr if it not in drop]


def _append_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    entry[target] = list(entry.get(target) or []) + _as_list(op.get("items"))


def _prepend_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    entry[target] = _as_list(op.get("items")) + list(entry.get(target) or [])


def _insert_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    arr = list(entry.get(target) or [])
    index = op.get("index")
    index = index if isinstance(index, int) else len(arr)
    entry[target] = arr[:index] + _as_list(op.get("items")) + arr[index:]


def _append_if_not_exists_arr(entry: dict[str, Any], target: str, op: dict[str, Any]) -> None:
    arr = list(entry.get(target) or [])
    for item in _as_list(op.get("items")):
        if item not in arr:
            arr.append(item)
    entry[target] = arr


def _set_prop(entry: dict[str, Any], _target: str, op: dict[str, Any]) -> None:
    """``{"prop": "vulnerable", "value": null}`` — a null value removes the property."""
    prop = op.get("prop")
    if not isinstance(prop, str):
        return
    if op.get("value") is None:
        entry.pop(prop, None)
    else:
        entry[prop] = op["value"]


def _add_skills(entry: dict[str, Any], _target: str, op: dict[str, Any]) -> None:
    """Skill bonuses are given as proficiency multipliers; the printed value is recomputed
    downstream from ability + proficiency, so record the raw entry and let the converter
    format it."""
    skills = op.get("skills")
    if not isinstance(skills, dict):
        return
    existing = dict(entry.get("skill") or {})
    for name, value in skills.items():
        existing.setdefault(str(name).lower(), value)
    entry["skill"] = existing


def _spellcasting_blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = entry.get("spellcasting")
    return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []


def _add_spells(entry: dict[str, Any], _target: str, op: dict[str, Any]) -> None:
    spells = op.get("spells")
    blocks = _spellcasting_blocks(entry)
    if not isinstance(spells, dict) or not blocks:
        return
    target_spells = dict(blocks[0].get("spells") or {})
    for level, payload in spells.items():
        slot = dict(target_spells.get(level) or {})
        incoming = payload.get("spells") if isinstance(payload, dict) else payload
        slot["spells"] = list(slot.get("spells") or []) + list(incoming or [])
        if isinstance(payload, dict) and "slots" in payload:
            slot["slots"] = payload["slots"]
        target_spells[level] = slot
    blocks[0]["spells"] = target_spells


def _remove_spells(entry: dict[str, Any], _target: str, op: dict[str, Any]) -> None:
    blocks = _spellcasting_blocks(entry)
    if not blocks:
        return
    for group in ("spells", "daily"):
        removals = op.get(group)
        if not isinstance(removals, dict):
            continue
        container = blocks[0].get(group)
        if not isinstance(container, dict):
            continue
        for level, names in removals.items():
            drop = set(names or [])
            current = container.get(level)
            if isinstance(current, dict) and isinstance(current.get("spells"), list):
                current["spells"] = [s for s in current["spells"] if s not in drop]
            elif isinstance(current, list):
                container[level] = [s for s in current if s not in drop]


def _replace_spells(entry: dict[str, Any], _target: str, op: dict[str, Any]) -> None:
    spells = op.get("spells")
    blocks = _spellcasting_blocks(entry)
    if not isinstance(spells, dict) or not blocks:
        return
    for group in ("spells", "daily"):
        container = blocks[0].get(group)
        if not isinstance(container, dict):
            continue
        for level, swaps in spells.items():
            current = container.get(level)
            mapping = {
                s.get("replace"): s.get("with")
                for s in _as_list(swaps) if isinstance(s, dict)
            }
            if isinstance(current, dict) and isinstance(current.get("spells"), list):
                current["spells"] = [mapping.get(s, s) for s in current["spells"]]
            elif isinstance(current, list):
                container[level] = [mapping.get(s, s) for s in current]


_MOD_HANDLERS = {
    "replaceTxt": _replace_txt,
    "replaceArr": _replace_arr,
    "removeArr": _remove_arr,
    "appendArr": _append_arr,
    "prependArr": _prepend_arr,
    "insertArr": _insert_arr,
    "appendIfNotExistsArr": _append_if_not_exists_arr,
    "setProp": _set_prop,
    "addSkills": _add_skills,
    "addSpells": _add_spells,
    "removeSpells": _remove_spells,
    "replaceSpells": _replace_spells,
}


def _apply_mods(entry: dict[str, Any], mod: dict[str, Any]) -> None:
    for target, ops in mod.items():
        for op in _as_list(ops):
            if not isinstance(op, dict):
                continue
            handler = _MOD_HANDLERS.get(op.get("mode"))
            if handler is not None:
                handler(entry, target, op)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def strip_noise(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in _NOISE_KEYS}


def resolve_copy(
    entry: dict[str, Any],
    index: MonsterIndex,
    _seen: Optional[frozenset[tuple[str, str]]] = None,
) -> dict[str, Any]:
    """Return ``entry`` with its ``_copy`` base merged in and ``_mod`` operations applied.

    Entries without ``_copy`` are returned unchanged (noise keys stripped). A base that is
    itself a ``_copy`` is resolved first — 13 chained copies exist in the bestiary. A missing
    or cyclic base degrades to the unresolved entry rather than raising, so one bad record
    cannot abort a 4,500-monster import.
    """
    spec = entry.get("_copy")
    if not isinstance(spec, dict):
        return strip_noise(entry)

    key = index_key(str(spec.get("name", "")), str(spec.get("source", "")))
    seen = _seen or frozenset()
    base = index.get(key)
    if base is None or key in seen:
        return strip_noise(entry)

    resolved_base = resolve_copy(base, index, seen | {key})
    merged = copy.deepcopy(resolved_base)
    for prop, value in entry.items():
        if prop != "_copy":
            merged[prop] = copy.deepcopy(value)

    mod = spec.get("_mod")
    if isinstance(mod, dict):
        _apply_mods(merged, mod)

    return strip_noise(merged)
