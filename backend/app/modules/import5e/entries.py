"""Flatten 5etools ``entries`` structures to plain text.

5etools nests prose as strings, lists, and typed dicts (``{"type": "list", "items": [...]}``,
``{"type": "entries", "name": ..., "entries": [...]}``). Several converters need the same
flattening, so it lives here rather than being duplicated per module.
"""

from __future__ import annotations

from typing import Any

from app.modules.import5e import tags


def to_text(entries: Any) -> str:
    """Flatten an ``entries`` structure (strings / nested dicts / lists) into one string."""
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
            for key in ("entries", "items", "rows", "entry"):
                if key in node:
                    walk(node[key])

    walk(entries)
    return tags.strip_tags(" ".join(p for p in parts if p))


def split_options(entries: Any) -> tuple[str, list[dict[str, str]], str]:
    """Split a lair/regional block into ``(intro, options, trailer)``.

    5etools writes these as leading prose, then a ``{"type": "list"}`` of the individual
    options, then optional closing prose ("If the dragon dies…"). Each list item becomes one
    named option; an item that is a dict with a ``name`` keeps it, otherwise the option is
    unnamed prose.
    """
    if not isinstance(entries, list):
        return (to_text(entries), [], "")

    intro: list[Any] = []
    trailer: list[Any] = []
    options: list[dict[str, str]] = []
    seen_list = False

    for node in entries:
        if isinstance(node, dict) and node.get("type") == "list":
            seen_list = True
            for item in node.get("items") or []:
                if isinstance(item, dict):
                    # Take the body only — `to_text` prepends a dict's own `name`, which
                    # would render as "Closing the Borders. Closing the Borders. …".
                    name = str(item.get("name", ""))
                    body = to_text(item.get("entries", item.get("entry", "")))
                else:
                    name, body = "", to_text(item)
                options.append({"name": name, "description": body})
        elif seen_list:
            trailer.append(node)
        else:
            intro.append(node)

    return (to_text(intro), options, to_text(trailer))
