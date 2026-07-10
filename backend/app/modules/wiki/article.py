"""Parse Tiptap (ProseMirror) article JSON: extract @mentions and a plain-text render.

Mentions are first-class nodes (``{"type": "mention", "attrs": {"id", "label"}}``), so
link extraction is lossless — the backbone of FR-2.2/2.3. Plain text feeds search
(Sprint 5) and the future AI corpus (ADR-012).
"""

from __future__ import annotations

from typing import Any

# Block-level nodes after which we insert a newline when flattening to text.
_BLOCK_TYPES = {
    "paragraph",
    "heading",
    "blockquote",
    "listItem",
    "bulletList",
    "orderedList",
    "codeBlock",
    "horizontalRule",
}


def extract_mention_ids(doc: dict[str, Any] | None) -> list[str]:
    """Distinct entity ids referenced by mention nodes, in document order."""
    ids: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "mention":
            mention_id = node.get("attrs", {}).get("id")
            if isinstance(mention_id, str) and mention_id not in seen:
                seen.add(mention_id)
                ids.append(mention_id)
        for child in node.get("content", []) or []:
            walk(child)

    walk(doc)
    return ids


def extract_plain_text(doc: dict[str, Any] | None) -> str:
    """Flatten the doc to text; mentions render as ``@label``."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        node_type = node.get("type")
        if node_type == "text":
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif node_type == "mention":
            label = node.get("attrs", {}).get("label") or node.get("attrs", {}).get("id", "")
            parts.append(f"@{label}")
        for child in node.get("content", []) or []:
            walk(child)
        if node_type in _BLOCK_TYPES:
            parts.append("\n")

    walk(doc)
    return "".join(parts).strip()
