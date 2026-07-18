"""Convert a 5etools bestiary entry into a ``dnd5e`` monster ``doc``.

The output matches ``_MONSTER_SCHEMA`` in ``app.modules.rules.systems.dnd5e``: required
``size, type, armor_class, hit_points, challenge_rating, abilities``; optional ``speed,
traits, actions, legendary_actions``. When a required field can't be built (special-only
AC/HP, missing abilities) the entry is skipped by returning ``None`` — the importer counts
it and moves on.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.modules.import5e import codes, legendary as legendary_mod, tags
from app.modules.import5e import entries as entries_mod

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_SPEED_ORDER = ("walk", "burrow", "climb", "fly", "swim")

#: 5etools skill keys use spaces; the plugin schema uses snake_case and a closed key set.
_SKILL_KEYS = {
    "acrobatics", "animal_handling", "arcana", "athletics", "deception", "history",
    "insight", "intimidation", "investigation", "medicine", "nature", "perception",
    "performance", "persuasion", "religion", "sleight_of_hand", "stealth", "survival",
}
_SENSE_KINDS = ("darkvision", "blindsight", "truesight", "tremorsense")
_SENSE_RE = re.compile(rf"({'|'.join(_SENSE_KINDS)})\s+(\d+)", re.IGNORECASE)
_TELEPATHY_RE = re.compile(r"telepathy\s+(\d+)", re.IGNORECASE)
_CASTER_LEVEL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)-level spellcaster", re.IGNORECASE)
#: "Tail Attack (Costs 2 Actions)" / "Breath Weapon (Recharge 5-6)" — the suffix is metadata,
#: not part of the action's name.
_COST_RE = re.compile(r"\s*\(costs?\s+(\d+)\s+actions?\)", re.IGNORECASE)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
#: Words that mean the regex has run past the attack's name into surrounding prose.
_MULTIATTACK_STOPWORDS = frozenset({
    "of", "which", "can", "be", "a", "an", "the", "only", "and", "or", "with", "its",
    "it", "makes", "make", "instead", "these", "those", "that", "this", "any", "either",
    "melee", "ranged", "weapon", "spell", "other",
})


#: Kept as a module-level alias: several tests and callers import it from here.
_entries_to_text = entries_mod.to_text


def _set(doc: dict[str, Any], key: str, value: Any) -> None:
    """Assign only when there's something to assign — every new field is optional, and an
    empty one must stay absent rather than becoming ``null`` in the stored document."""
    if value not in (None, "", [], {}):
        doc[key] = value


def parse_cr(cr: Any) -> Optional[float]:
    """``"1/4"`` -> 0.25, ``"10"`` -> 10.0, ``{"cr": "5"}`` -> 5.0."""
    if isinstance(cr, dict):
        cr = cr.get("cr")
    if isinstance(cr, (int, float)):
        return float(cr)
    if not isinstance(cr, str):
        return None
    cr = cr.strip()
    if cr in ("", "—", "-", "Unknown"):
        return None
    if "/" in cr:
        num, _, den = cr.partition("/")
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(cr)
    except ValueError:
        return None


def _xp(cr_field: Any, cr: Optional[float]) -> Optional[int]:
    """XP for the entry: an explicit ``{"cr": ..., "xp": N}`` override wins, else the CR table.

    5etools has no standalone ``xp`` field, so omitting this leaves every monster at 0 XP and
    ``encounter_difficulty()`` rates every encounter "trivial".
    """
    if isinstance(cr_field, dict):
        explicit = cr_field.get("xp")
        if isinstance(explicit, (int, float)):
            return int(explicit)
    return codes.xp_for_cr(cr)


def _type_str(type_field: Any) -> Optional[str]:
    """``"humanoid"`` or ``{"type": "humanoid", "tags": [...]}`` -> ``"humanoid"``."""
    if isinstance(type_field, str):
        return type_field
    if isinstance(type_field, dict):
        inner = type_field.get("type")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, dict):  # {"choose": [...]}
            choices = inner.get("choose")
            if isinstance(choices, list) and choices:
                return str(choices[0])
    return None


def _armor_class(ac_field: Any) -> tuple[Optional[int], Optional[str]]:
    """The creature's base AC and the parenthetical that explains it.

    Entries carrying a ``condition`` are situational ("18 while in bear form"); taking the
    first entry blindly picks those for shapechangers, so unconditional entries win.
    """
    if isinstance(ac_field, int):
        return ac_field, None
    if not isinstance(ac_field, list) or not ac_field:
        return None, None

    def value(item: Any) -> Optional[int]:
        if isinstance(item, int):
            return item
        if isinstance(item, dict) and isinstance(item.get("ac"), int):
            return item["ac"]
        return None

    unconditional = [
        item for item in ac_field
        if isinstance(item, int) or (isinstance(item, dict) and "condition" not in item)
    ]
    chosen = next((item for item in (unconditional or ac_field) if value(item) is not None), None)
    if chosen is None:
        return None, None
    note = None
    if isinstance(chosen, dict):
        parts = [*(chosen.get("from") or []), chosen.get("condition") or ""]
        note = tags.strip_tags(", ".join(p for p in parts if p)) or None
    return value(chosen), note


def _hit_points(hp_field: Any) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """``(hit_points, hit_dice, note)``.

    A ``special`` HP entry is usually prose ("immune to damage") but is sometimes just a
    number, so it is worth an int parse before giving up on the monster entirely.
    """
    if isinstance(hp_field, int):
        return hp_field, None, None
    if not isinstance(hp_field, dict):
        return None, None, None
    formula = hp_field.get("formula")
    formula = str(formula) if isinstance(formula, str) else None
    avg = hp_field.get("average")
    if isinstance(avg, (int, float)):
        return int(avg), formula, None
    special = hp_field.get("special")
    if isinstance(special, str):
        text = tags.strip_tags(special)
        digits = re.match(r"\s*(\d+)", text)
        return (int(digits.group(1)) if digits else None), formula, text
    return None, formula, None


def _abilities(entry: dict[str, Any]) -> Optional[dict[str, int]]:
    out: dict[str, int] = {}
    for ab in _ABILITIES:
        val = entry.get(ab)
        if not isinstance(val, int) or not (1 <= val <= 30):
            return None
        out[ab] = val
    return out


def _speed_str(speed: Any) -> Optional[str]:
    if isinstance(speed, (int, float)):
        return f"{int(speed)} ft."
    if not isinstance(speed, dict):
        return None
    parts: list[str] = []
    for key in _SPEED_ORDER:
        val = speed.get(key)
        if val is None:
            continue
        if isinstance(val, dict):  # {"number": 40, "condition": "(hover)"}
            num = val.get("number")
            cond = val.get("condition", "")
            text = f"{num} ft. {cond}".strip()
        else:
            text = f"{val} ft."
        parts.append(text if key == "walk" else f"{key} {text}")
    return ", ".join(parts) or None


def _traits(entry: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for t in entry.get("trait", []) or []:
        name = t.get("name")
        desc = _entries_to_text(t.get("entries"))
        if name or desc:
            out.append({"name": name or "", "description": desc})
    return out


def _attack(action: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = action.get("name")
    if not name:
        return None
    raw = " ".join(str(e) for e in action.get("entries", []) if isinstance(e, str))
    clean_name, cost = _split_cost(str(name))
    atk: dict[str, Any] = {"name": clean_name}
    if cost is not None:
        atk["cost"] = cost
    kind = tags.attack_kind(raw)
    if kind:
        atk["kind"] = kind
    hit = tags.to_hit(raw)
    if hit is not None:
        atk["to_hit"] = hit
    # Every damage instance with its type — a rider ("plus 2d6 fire") is a separate part.
    damage = tags.damage_parts(raw)
    if not damage:
        dice = tags.first_damage(raw)
        if dice:
            damage = [{"dice": dice}]
    if damage:
        atk["damage"] = damage
    desc = _entries_to_text(action.get("entries"))
    if desc:
        atk["description"] = desc
    return atk


def _split_cost(name: str) -> tuple[str, Optional[int]]:
    """``"Tail Attack (Costs 2 Actions)"`` -> ``("Tail Attack", 2)``."""
    match = _COST_RE.search(name)
    if not match:
        return name.strip(), None
    return _COST_RE.sub("", name).strip(), int(match.group(1))


def _attacks(actions: Any) -> list[dict[str, Any]]:
    return [a for a in (_attack(x) for x in actions or [] if isinstance(x, dict)) if a]


def _legendary(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
    legendary = entry.get("legendary")
    if not isinstance(legendary, list) or not legendary:
        return None
    options: list[dict[str, Any]] = []
    for opt in legendary:
        attack = _attack(opt)
        if attack is not None:
            # The schema caps a legendary cost at 3; anything odd falls back to the default.
            if not 1 <= int(attack.get("cost", 1)) <= 3:
                attack.pop("cost", None)
            options.append(attack)
    if not options:
        return None
    # Most creatures get 3 per round, but the count is stated when it differs (2 or 5).
    count = entry.get("legendaryActions")
    out: dict[str, Any] = {
        "count": int(count) if isinstance(count, int) and 1 <= count <= 5 else 3,
        "options": options,
    }
    header = _entries_to_text(entry.get("legendaryHeader"))
    if header:
        out["description"] = header
    return out


def _modifier_map(field: Any, allowed: Any) -> Optional[dict[str, int]]:
    """``{"con": "+6"}`` -> ``{"con": 6}``, dropping keys outside ``allowed``."""
    if not isinstance(field, dict):
        return None
    out: dict[str, int] = {}
    for key, value in field.items():
        norm = str(key).strip().lower().replace(" ", "_")
        if norm not in allowed:
            continue  # 5etools ships pseudo-skills ("other") the schema doesn't model
        try:
            out[norm] = int(str(value).replace("+", "").strip())
        except ValueError:
            continue
    return out or None


def _senses(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
    raw = entry.get("senses")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None
    out: dict[str, Any] = {}
    other: list[str] = []
    for item in raw:
        text = tags.strip_tags(str(item))
        match = _SENSE_RE.search(text)
        if match:
            out[match.group(1).lower()] = int(match.group(2))
            if "blind beyond" in text.lower():
                out["blind_beyond"] = True
        elif text:
            other.append(text)
    if other:
        out["other"] = other
    return out or None


def _languages(entry: dict[str, Any]) -> tuple[Optional[list[str]], Optional[int]]:
    """Language list plus telepathy range, which 5etools files in with the languages."""
    raw = entry.get("languages")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None, None
    langs: list[str] = []
    telepathy: Optional[int] = None
    for item in raw:
        text = tags.strip_tags(str(item)).strip()
        if not text:
            continue
        match = _TELEPATHY_RE.search(text)
        if match:
            telepathy = int(match.group(1))
            continue  # not a language — it's a sense filed under languages
        langs.append(text)
    return (langs or None), telepathy


def _damage_groups(field: Any, key: str) -> Optional[list[dict[str, Any]]]:
    """Normalise 5etools' damage resist/immune/vulnerable forms.

    Entries are a bare string, or ``{"<key>": [...], "note": ..., "cond": true}`` where the
    inner list may itself nest the same structure, or ``{"special": "..."}``.
    """
    if not isinstance(field, list) or not field:
        return None
    specials: list[dict[str, Any]] = []
    # Types sharing a qualifier belong in one group: "bludgeoning, piercing and slashing
    # from nonmagical attacks" is a single printed line, not three.
    by_note: dict[str, list[str]] = {}

    def walk(items: Any, note: str) -> None:
        for item in items or []:
            if isinstance(item, str):
                by_note.setdefault(note, []).append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("special"), str):
                    specials.append({"special": tags.strip_tags(item["special"])})
                    continue
                inner_note = " ".join(
                    part for part in (item.get("preNote"), item.get("note")) if part
                ).strip() or note
                walk(item.get(key), inner_note)

    walk(field, "")
    groups: list[dict[str, Any]] = []
    for note, types in by_note.items():
        group: dict[str, Any] = {"types": types}
        if note:
            group["note"] = note
        groups.append(group)
    return (groups + specials) or None


def _is_multiattack(name: Any) -> bool:
    return isinstance(name, str) and name.strip().lower().startswith("multiattack")


def _multiattack(actions: Any) -> Optional[dict[str, Any]]:
    """Pull the Multiattack entry out of ``actions`` — it describes them, it isn't one."""
    for item in actions or []:
        # "Multiattack (Vampire Form Only)" is still a multiattack — match the prefix.
        if isinstance(item, dict) and _is_multiattack(item.get("name")):
            description = _entries_to_text(item.get("entries"))
            out: dict[str, Any] = {"description": description}
            parsed = _parse_multiattack(description)
            if parsed:
                out["attacks"] = parsed
            return out
    return None


def _parse_multiattack(text: str) -> list[dict[str, Any]]:
    """Best-effort "makes two claw attacks and one bite attack" -> [{Claw, 2}, {Bite, 1}].

    Deliberately conservative. ``description`` is always kept, so failing to parse costs
    nothing, while a wrong guess ("Of Which Can Be A Bite", from "two attacks, only one of
    which can be a bite attack") would put nonsense in the UI. Only a one- or two-word name
    made entirely of non-filler words is accepted.
    """
    out: list[dict[str, Any]] = []
    for count_word, name in re.findall(
        r"\b(one|two|three|four|five|six)\s+([a-z']+(?:\s+[a-z']+)?)\s+attacks?\b",
        text, re.IGNORECASE,
    ):
        words = name.lower().split()
        if any(w in _MULTIATTACK_STOPWORDS for w in words):
            continue
        label = name.strip().rstrip("s").title()
        if label:
            out.append({"name": label, "count": _NUMBER_WORDS[count_word.lower()]})
    return out


def _spellcasting(entry: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    blocks = entry.get("spellcasting")
    if not isinstance(blocks, list) or not blocks:
        return None
    out: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        converted = _spellcasting_block(block)
        if converted:
            out.append(converted)
    return out or None


def _spellcasting_block(block: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = str(block.get("name") or "Spellcasting")
    header_raw = " ".join(str(e) for e in block.get("headerEntries") or [] if isinstance(e, str))
    out: dict[str, Any] = {
        "name": name,
        "kind": "innate" if "innate" in name.lower() else "prepared",
    }
    ability = block.get("ability")
    if ability in _ABILITIES:
        out["ability"] = ability
    dc = tags.first_tag(header_raw, "dc")
    if dc and dc.split("|", 1)[0].strip().isdigit():
        out["save_dc"] = int(dc.split("|", 1)[0].strip())
    attack_bonus = tags.to_hit(header_raw)
    if attack_bonus is not None:
        out["attack_bonus"] = attack_bonus
    level = _CASTER_LEVEL_RE.search(header_raw)
    if level and 1 <= int(level.group(1)) <= 20:
        out["caster_level"] = int(level.group(1))
    description = _entries_to_text(block.get("headerEntries"))
    if description:
        out["description"] = description

    at_will = [tags.strip_tags(s) for s in block.get("will") or [] if isinstance(s, str)]
    if at_will:
        out["at_will"] = at_will

    per_day: list[dict[str, Any]] = []
    for key, spells in (block.get("daily") or {}).items():
        digits = str(key).rstrip("e")
        if not digits.isdigit():
            continue
        names = [tags.strip_tags(s) for s in spells or [] if isinstance(s, str)]
        if names:
            # A trailing "e" means "each": "3e" is 3/day *each*, not 3/day between them.
            per_day.append({"uses": int(digits), "each": str(key).endswith("e"),
                            "spells": names})
    if per_day:
        out["per_day"] = sorted(per_day, key=lambda p: -p["uses"])

    slots: list[dict[str, Any]] = []
    for key, payload in (block.get("spells") or {}).items():
        if not str(key).isdigit():
            continue
        level_num = int(key)
        names = [
            tags.strip_tags(s)
            for s in (payload.get("spells") if isinstance(payload, dict) else payload) or []
            if isinstance(s, str)
        ]
        slot: dict[str, Any] = {"level": level_num}
        if isinstance(payload, dict) and isinstance(payload.get("slots"), int):
            slot["slots"] = payload["slots"]
        if names:
            slot["spells"] = names
        slots.append(slot)
    if slots:
        out["slots"] = sorted(slots, key=lambda s: s["level"])

    return out if (at_will or per_day or slots or description) else None


def to_monster_doc(
    entry: dict[str, Any],
    legendary_groups: Optional[legendary_mod.GroupIndex] = None,
) -> Optional[dict[str, Any]]:
    """Reshape one 5etools ``monster`` entry into a ``dnd5e`` doc, or ``None`` to skip it.

    ``legendary_groups`` is the index from ``legendarygroups.json``; without it lair actions
    and regional effects are omitted, since they are not stored on the monster entry itself.
    Pass a ``_copy``-resolved entry (see ``copyres``) — a raw variant has no body to convert.
    """
    size = codes.size_name(entry.get("size"))
    mtype = _type_str(entry.get("type"))
    armor_class, ac_note = _armor_class(entry.get("ac"))
    hit_points, hit_dice, hp_note = _hit_points(entry.get("hp"))
    cr = parse_cr(entry.get("cr"))
    abilities = _abilities(entry)
    if None in (size, mtype, armor_class, hit_points, cr) or abilities is None:
        return None

    doc: dict[str, Any] = {
        "size": size,
        "type": mtype,
        "armor_class": armor_class,
        "hit_points": hit_points,
        "challenge_rating": cr,
        "abilities": abilities,
    }
    xp = _xp(entry.get("cr"), cr)
    if xp is not None:
        doc["xp"] = xp
    speed = _speed_str(entry.get("speed"))
    if speed:
        doc["speed"] = speed
    traits = _traits(entry)
    if traits:
        doc["traits"] = traits

    # --- defenses and senses ---------------------------------------------- #
    _set(doc, "alignment", codes.alignment_str(entry.get("alignment")))
    _set(doc, "armor_class_note", ac_note)
    _set(doc, "hit_dice", hit_dice)
    _set(doc, "hit_points_note", hp_note)
    _set(doc, "saving_throws", _modifier_map(entry.get("save"), _ABILITIES))
    _set(doc, "skills", _modifier_map(entry.get("skill"), _SKILL_KEYS))
    _set(doc, "senses", _senses(entry))
    languages, telepathy = _languages(entry)
    _set(doc, "languages", languages)
    _set(doc, "telepathy", telepathy)
    _set(doc, "damage_resistances", _damage_groups(entry.get("resist"), "resist"))
    _set(doc, "damage_immunities", _damage_groups(entry.get("immune"), "immune"))
    _set(doc, "damage_vulnerabilities",
         _damage_groups(entry.get("vulnerable"), "vulnerable"))
    condition_immunities = _damage_groups(entry.get("conditionImmune"), "conditionImmune")
    if condition_immunities:
        # Flattened: conditions carry no "from nonmagical" style qualifier worth keeping.
        flat = [t for group in condition_immunities for t in group.get("types", [])]
        _set(doc, "condition_immunities", flat or None)

    # --- actions ----------------------------------------------------------- #
    _set(doc, "multiattack", _multiattack(entry.get("action")))
    # Multiattack describes the other actions rather than being one, so it is hoisted out.
    actions = [a for a in _attacks(entry.get("action")) if not _is_multiattack(a["name"])]
    if actions:
        doc["actions"] = actions
    _set(doc, "bonus_actions", _attacks(entry.get("bonus")) or None)
    _set(doc, "reactions", _attacks(entry.get("reaction")) or None)
    _set(doc, "spellcasting", _spellcasting(entry))

    group = legendary_mod.group_for(entry, legendary_groups or {})
    _set(doc, "lair_actions", legendary_mod.lair_actions(group))
    _set(doc, "regional_effects", legendary_mod.regional_effects(group))

    _set(doc, "source", entry.get("source") if isinstance(entry.get("source"), str) else None)
    page = entry.get("page")
    _set(doc, "page", int(page) if isinstance(page, int) and page > 0 else None)

    legendary = _legendary(entry)
    if legendary:
        doc["legendary_actions"] = legendary
    return doc
