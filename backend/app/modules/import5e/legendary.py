"""Lair actions and regional effects from the 5etools ``legendarygroups.json`` file.

These are not stored on the monster. A creature that has them carries
``"legendaryGroup": {"name": ..., "source": ...}``, which points into a separate file of 187
shared groups (115 with lair actions, 157 with regional effects). Without joining that file
no monster in the bestiary has a lair action at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.import5e import entries, sources

GroupIndex = dict[tuple[str, str], dict[str, Any]]

#: 5e's initiative count for lair actions.
_LAIR_INITIATIVE = 20


def _key(name: str, source: str) -> tuple[str, str]:
    return (name.strip().lower(), source.strip().lower())


def load_groups(bestiary_dir: Path) -> GroupIndex:
    """Index ``legendarygroups.json`` by ``(name, source)``. Empty if the file is absent."""
    path = bestiary_dir / "legendarygroups.json"
    if not path.exists():
        return {}
    index: GroupIndex = {}
    for group in sources.load_json(path).get("legendaryGroup", []):
        name, source = group.get("name"), group.get("source")
        if isinstance(name, str) and isinstance(source, str):
            index[_key(name, source)] = group
    return index


def group_for(entry: dict[str, Any], index: GroupIndex) -> dict[str, Any] | None:
    """The legendary group a monster entry points at, if any."""
    spec = entry.get("legendaryGroup")
    if not isinstance(spec, dict):
        return None
    return index.get(_key(str(spec.get("name", "")), str(spec.get("source", ""))))


def lair_actions(group: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a group's ``lairActions`` into the plugin's ``lair_actions`` shape."""
    if not group or not group.get("lairActions"):
        return None
    description, options, _ = entries.split_options(group["lairActions"])
    if not description and not options:
        return None
    out: dict[str, Any] = {"initiative": _LAIR_INITIATIVE}
    if description:
        out["description"] = description
    if options:
        out["options"] = options
    return out


def regional_effects(group: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a group's ``regionalEffects`` into the plugin's ``regional_effects`` shape."""
    if not group or not group.get("regionalEffects"):
        return None
    description, effects, fades = entries.split_options(group["regionalEffects"])
    if not description and not effects:
        return None
    out: dict[str, Any] = {}
    if description:
        out["description"] = description
    if effects:
        out["effects"] = effects
    if fades:  # "If the dragon dies, these effects fade over 1d10 days."
        out["fades"] = fades
    return out
