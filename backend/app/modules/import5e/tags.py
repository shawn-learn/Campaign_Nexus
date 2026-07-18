"""Strip and read 5etools ``{@tag ...}`` inline markup.

5etools laces its text fields with mini-templates: ``{@hit 4}``, ``{@damage 1d6+2}``,
``{@atk mw}``, ``{@dc 13}``, ``{@item leather armor|phb}``, ``{@condition prone}``,
``{@spell fireball}``, ``{@scaledamage 8d6|3-9|1d6}``. The general display rule is "keep
the first ``|``-segment of the payload, drop the tag wrapper"; a few tags render specially.
"""

from __future__ import annotations

import re
from typing import Optional

# One ``{@tag payload}`` occurrence. Payload is everything up to the matching brace; we do
# not need to handle nesting (5etools does not nest tags inside a tag's own payload here).
_TAG_RE = re.compile(r"\{@(\w+)\s*([^{}]*)\}")

# Attack-type codes -> our monster attack ``kind``. Melee/ranged weapon or spell attacks.
_ATK_KIND = {
    "mw": "melee", "rw": "ranged", "ms": "melee", "rs": "ranged",
    "m": "melee", "r": "ranged",
}


def _first_seg(payload: str) -> str:
    """The display text of a ``|``-delimited payload: ``leather armor|phb`` -> ``leather armor``."""
    return payload.split("|", 1)[0].strip()


def _render_tag(tag: str, payload: str) -> str:
    """Turn a single tag into the plain text it should display as."""
    if tag == "atk":
        # ``{@atk mw}`` -> "Melee Weapon Attack"; leave unknown codes as-is.
        codes = {
            "mw": "Melee Weapon Attack", "rw": "Ranged Weapon Attack",
            "ms": "Melee Spell Attack", "rs": "Ranged Spell Attack",
        }
        return codes.get(payload.strip(), payload.strip())
    if tag == "h":
        return "Hit:"
    if tag == "hit":
        # ``{@hit 4}`` -> "+4"
        seg = _first_seg(payload)
        return f"+{seg}" if seg and not seg.startswith(("+", "-")) else seg
    if tag == "dc":
        return f"DC {_first_seg(payload)}"
    if tag in ("scaledamage", "scaledice"):
        # ``{@scaledamage 8d6|3-9|1d6}`` -> the base dice ("8d6").
        return _first_seg(payload)
    if tag in ("recharge",):
        seg = _first_seg(payload)
        return f"(Recharge {seg})" if seg else "(Recharge)"
    # damage, dice, item, spell, condition, creature, chance, skill, action, sense, quickref…
    return _first_seg(payload)


def strip_tags(text: Optional[str]) -> str:
    """Return ``text`` with every ``{@tag}`` replaced by its plain-text rendering."""
    if not text:
        return ""
    prev = None
    out = text
    # Loop in case a rendering re-exposes a brace boundary; bounded by shrinking length.
    while prev != out:
        prev = out
        out = _TAG_RE.sub(lambda m: _render_tag(m.group(1), m.group(2)), out)
    return out.strip()


def first_tag(text: Optional[str], tag: str) -> Optional[str]:
    """The raw payload of the first ``{@tag ...}`` of the given kind, or ``None``."""
    if not text:
        return None
    for m in _TAG_RE.finditer(text):
        if m.group(1) == tag:
            return m.group(2).strip()
    return None


def attack_kind(text: Optional[str]) -> Optional[str]:
    """Read the attack ``kind`` (melee|ranged) from a ``{@atk ...}`` tag, if present."""
    payload = first_tag(text, "atk")
    if payload is None:
        return None
    code = payload.split("|", 1)[0].strip().lower()
    return _ATK_KIND.get(code)


def to_hit(text: Optional[str]) -> Optional[int]:
    """Read the integer attack bonus from a ``{@hit N}`` tag, if present."""
    payload = first_tag(text, "hit")
    if payload is None:
        return None
    seg = _first_seg(payload).lstrip("+")
    try:
        return int(seg)
    except ValueError:
        return None


#: A ``{@damage …}`` followed by its damage type. 5etools writes "5 ({@damage 1d6 + 2})
#: slashing damage", and riders as "plus 7 ({@damage 2d6}) fire damage" — so the type is the
#: word (or two, for "force" vs "bludgeoning") immediately before "damage".
_DAMAGE_PART_RE = re.compile(
    r"\{@damage\s+([^}|]+?)(?:\|[^}]*)?\}\s*\)?\s*(?:[a-z]+\s+)??([a-z]+)\s+damage",
    re.IGNORECASE,
)


def damage_parts(text: Optional[str]) -> list[dict[str, str]]:
    """Every damage instance in a line as ``{"dice", "type"}``.

    ``first_damage`` returns only the first expression and no type at all, which loses both
    the damage type and any "plus 2d6 fire" rider.
    """
    if not text:
        return []
    parts: list[dict[str, str]] = []
    for match in _DAMAGE_PART_RE.finditer(text):
        dice = match.group(1).replace(" ", "")
        if dice:
            parts.append({"dice": dice, "type": match.group(2).lower()})
    return parts


def first_damage(text: Optional[str]) -> Optional[str]:
    """Read the first ``{@damage XdY+Z}`` dice expression, whitespace-normalised."""
    payload = first_tag(text, "damage")
    if payload is None:
        return None
    dice = _first_seg(payload).replace(" ", "")
    return dice or None
