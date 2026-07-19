"""Fold the "Appendix C: Treasures" note into the individual equipment articles.

The appendix is a single note holding the full description of seven treasures.
Each item now has its own catalog entity, so the note is redundant as a
container: this splits it on its ``H2`` headings, writes each section as the
matching equipment's article, then soft-deletes the note.

The lead paragraph (which explains that the Tarokka reading places three of the
treasures) is carried onto each of those three items, since it is about them.
The "MAGIC ITEMS" divider and its one-line preamble are structural and are
dropped.

Idempotent: an item that already has an article is left untouched, and a note
that is already deleted is left alone.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import SessionLocal
from app.db_metadata import metadata  # noqa: F401 — imports models + registers projectors
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from sqlalchemy import select

CAMPAIGN_ID = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd
APPENDIX_ID = "019f51db-36d4-7d95-852b-70dc1f656f5a"  # Appendix C: Treasures

# Appendix heading -> equipment entity name.
TARGETS = {
    "TOME OF STRAHD": "Tome of Strahd",
    "BLOOD SPEAR": "Blood Spear",
    "GULTHIAS STAFF": "Gulthias Staff",
    "HOLY SYMBOL OF RAVENKIND": "Holy Symbol of Ravenkind",
    "ICON OF RAVENLOFT": "Icon of Ravenloft",
    "SAINT MARKOVIA'S THIGHBONE": "Saint Markovia's Thighbone",
    "SUNSWORD": "Sunsword",
}

# The three treasures the lead paragraph is about.
FORTUNES = ("TOME OF STRAHD", "HOLY SYMBOL OF RAVENKIND", "SUNSWORD")

# Structural nodes with no item-specific content.
DROP_HEADINGS = ("MAGIC ITEMS",)


def _heading_text(node: dict) -> str:
    return "".join(c.get("text", "") for c in node.get("content", [])).strip()


def _split(doc: dict) -> tuple[dict | None, dict[str, list[dict]]]:
    """Return (lead paragraph, {heading: body nodes}) from the appendix doc."""
    lead: dict | None = None
    sections: dict[str, list[dict]] = {}
    current: str | None = None
    for node in doc["content"]:
        if node["type"] == "heading":
            title = _heading_text(node)
            if title in TARGETS:
                current = title
                sections[current] = []
            else:
                # A divider such as "MAGIC ITEMS" ends the previous section.
                current = None
            continue
        if current is not None:
            sections[current].append(node)
        elif lead is None and node["type"] == "paragraph":
            lead = node
    return lead, sections


def main() -> None:
    with SessionLocal() as session:
        note = session.get(Entity, APPENDIX_ID)
        if note is None:
            print(f"Error: note {APPENDIX_ID} not found.")
            sys.exit(1)
        if note.deleted_at_real is not None:
            print("Appendix C is already deleted — nothing to do.")
            return

        lead, sections = _split(json.loads(note.article_json))
        missing = set(TARGETS) - set(sections)
        if missing:
            print(f"Error: appendix has no section for {sorted(missing)} — aborting.")
            sys.exit(1)

        moved = 0
        for heading, body in sections.items():
            name = TARGETS[heading]
            target = session.scalar(
                select(Entity).where(
                    Entity.campaign_id == CAMPAIGN_ID,
                    Entity.entity_type == "equipment",
                    Entity.name == name,
                    Entity.deleted_at_real.is_(None),
                )
            )
            if target is None:
                print(f"  ! no equipment entity named {name!r} — aborting before delete.")
                sys.exit(1)
            if target.article_text:
                print(f"  = {name}: already has an article, left alone.")
                continue

            content = list(body)
            if heading in FORTUNES and lead is not None:
                content.insert(0, lead)
            wiki_service.update_article(
                session, CAMPAIGN_ID, target.id, article_json={"type": "doc", "content": content}
            )
            moved += 1
            print(f"  + {name}: {len(content)} block(s) written.")

        wiki_service.soft_delete_entity(session, CAMPAIGN_ID, APPENDIX_ID)
        print(f"\nDone. {moved} article(s) written; Appendix C soft-deleted.")


if __name__ == "__main__":
    main()
