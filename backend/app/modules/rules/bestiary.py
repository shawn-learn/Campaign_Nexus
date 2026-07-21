"""Bestiary: import SRD content packs and query monsters by plugin-defined facets."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.rules import registry
from app.modules.rules.models import Monster, StatBlock


class MonsterNotFound(LookupError):
    pass


class MonsterNotEditable(ValueError):
    """A pack-owned monster can't be deleted — the pack owns it (use a variant instead)."""


def _facets(system_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    values = registry.get_system(system_id).monster_facets(doc)
    return {
        "facet1_num": values.get("facet1_num"),
        "facet2_num": values.get("facet2_num"),
        "facet1_text": values.get("facet1_text"),
        "facet2_text": values.get("facet2_text"),
    }


def _to_out(session: Session, monster: Monster) -> dict[str, Any]:
    block = session.get(StatBlock, monster.stat_block_id)
    return {
        "id": monster.id,
        "name": monster.name,
        "source": monster.source,
        "variant_of": monster.variant_of,
        "rule_system_id": block.rule_system_id if block else "",
        "sheet_type": "monster",
        "stat_block_id": monster.stat_block_id,
        "doc": json.loads(block.doc_json) if block else {},
        "derived": json.loads(block.derived_json) if block else {},
        "facets": {
            "facet1_num": monster.facet1_num,
            "facet2_num": monster.facet2_num,
            "facet1_text": monster.facet1_text,
            "facet2_text": monster.facet2_text,
        },
    }


def _create_monster(
    session: Session, campaign_id: str, system_id: str, name: str, doc: dict[str, Any],
    *, source: str, variant_of: str | None = None,
) -> Monster:
    system = registry.get_system(system_id)
    derived = system.derive("monster", doc)
    block = StatBlock(
        id=new_id(),
        campaign_id=campaign_id,
        rule_system_id=system_id,
        sheet_type="monster",
        schema_version=system.version,
        label=name,
        doc_json=json.dumps(doc),
        derived_json=json.dumps(derived),
    )
    session.add(block)
    session.flush()
    facets = _facets(system_id, doc)
    monster = Monster(
        id=new_id(), campaign_id=campaign_id, name=name, stat_block_id=block.id,
        source=source, variant_of=variant_of, **facets,
    )
    session.add(monster)
    return monster


def _refresh_monster(
    session: Session, system_id: str, monster: Monster, doc: dict[str, Any], source: str
) -> None:
    """Rewrite a pack-sourced monster's stat block from the pack's current content."""
    block = session.get(StatBlock, monster.stat_block_id)
    if block is not None:
        block.doc_json = json.dumps(doc)
        block.derived_json = json.dumps(registry.get_system(system_id).derive("monster", doc))
        block.schema_version = registry.get_system(system_id).version
    for key, value in _facets(system_id, doc).items():
        setattr(monster, key, value)
    monster.source = source


def import_content_packs(session: Session, campaign_id: str, system_id: str) -> int:
    """Materialize a system's SRD packs into the campaign bestiary, and keep them current.

    Idempotent while the pack version holds still: same version, nothing to do. When the
    version moves, pack-sourced monsters are **rewritten** from the pack rather than
    duplicated — matching on name within the same pack id, not the versioned source string.

    That matching matters. Keying `existing` off the full versioned source (as this did)
    meant a version bump found nothing existing and re-imported the whole pack alongside the
    old copies: two Goblins, forever. And never bumping meant a pack could never correct or
    extend anything it had already shipped.

    Only monsters this pack owns are touched. A ``custom`` variant (``make_variant``) or an
    ``imported`` monster is the GM's own — rewriting those would defeat the point of
    copy-on-write (FR-11.4), which is exactly the mechanism for customizing a pack monster.
    """
    system = registry.get_system(system_id)
    changed = 0
    for pack in system.content_packs():
        source = f"content_pack:{pack['id']}@{pack['version']}"
        owned = f"content_pack:{pack['id']}@"
        existing = {
            m.name: m
            for m in session.scalars(
                select(Monster).where(
                    Monster.campaign_id == campaign_id,
                    Monster.source.startswith(owned),
                )
            )
        }
        for entry in pack.get("monsters", []):
            monster = existing.get(entry["name"])
            if monster is None:
                _create_monster(
                    session, campaign_id, system_id, entry["name"], entry["doc"], source=source
                )
                changed += 1
            elif monster.source != source:  # the pack moved on; bring this one with it
                _refresh_monster(session, system_id, monster, entry["doc"], source)
                changed += 1
    session.commit()
    return changed


def create_custom_monster(
    session: Session,
    campaign_id: str,
    system_id: str,
    *,
    name: str,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a blank custom monster (``source="custom"``) to author from scratch.

    The starting document is the plugin's own ``blank_doc`` (already schema-valid) unless the
    caller supplies one, so a freshly created monster saves and edits like any other.
    """
    system = registry.get_system(system_id)
    base = system.blank_doc("monster")
    if doc:
        base = {**base, **doc}
    errors = system.validate("monster", base)
    if errors:
        raise ValueError("; ".join(errors))
    monster = _create_monster(
        session, campaign_id, system_id, name, base, source="custom",
    )
    session.commit()
    return _to_out(session, monster)


def delete_monster(session: Session, campaign_id: str, monster_id: str) -> None:
    """Delete a GM-authored monster (custom or imported) and the stat block behind it.

    Pack-owned monsters are the pack's, not the GM's — deleting one would just be undone by the
    next content import, so it's refused (``MonsterNotEditable``); the GM makes a variant to own
    a copy instead.
    """
    monster = session.get(Monster, monster_id)
    if monster is None or monster.campaign_id != campaign_id:
        raise MonsterNotFound(monster_id)
    if monster.source.startswith("content_pack:"):
        raise MonsterNotEditable(monster_id)
    block = session.get(StatBlock, monster.stat_block_id)
    session.delete(monster)
    if block is not None:
        session.delete(block)
    session.commit()


def make_variant(session: Session, campaign_id: str, monster_id: str) -> dict[str, Any]:
    """Copy-on-write clone of a monster into the campaign as a custom variant (FR-11.4)."""
    original = session.get(Monster, monster_id)
    if original is None or original.campaign_id != campaign_id:
        raise MonsterNotFound(monster_id)
    block = session.get(StatBlock, original.stat_block_id)
    if block is None:
        raise MonsterNotFound(monster_id)
    variant = _create_monster(
        session, campaign_id, block.rule_system_id, f"{original.name} (variant)",
        json.loads(block.doc_json), source="custom", variant_of=original.id,
    )
    session.commit()
    return _to_out(session, variant)


def list_monsters(
    session: Session,
    campaign_id: str,
    *,
    q: str | None = None,
    facet1_num_gte: float | None = None,
    facet1_num_lte: float | None = None,
    facet1_text: str | None = None,
    facet2_text: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = select(Monster).where(Monster.campaign_id == campaign_id)
    if q:
        stmt = stmt.where(Monster.name.ilike(f"%{q}%"))
    if facet1_num_gte is not None:
        stmt = stmt.where(Monster.facet1_num >= facet1_num_gte)
    if facet1_num_lte is not None:
        stmt = stmt.where(Monster.facet1_num <= facet1_num_lte)
    if facet1_text:
        stmt = stmt.where(func.lower(Monster.facet1_text) == facet1_text.lower())
    if facet2_text:
        stmt = stmt.where(Monster.facet2_text == facet2_text)
    stmt = stmt.order_by(Monster.facet1_num, Monster.name).limit(limit)
    return [_to_out(session, m) for m in session.scalars(stmt)]


def get_monster(session: Session, campaign_id: str, monster_id: str) -> dict[str, Any]:
    monster = session.get(Monster, monster_id)
    if monster is None or monster.campaign_id != campaign_id:
        raise MonsterNotFound(monster_id)
    return _to_out(session, monster)


# --------------------------------------------------------------------------- #
# JSON import / export
# --------------------------------------------------------------------------- #
def export_monsters(session: Session, campaign_id: str) -> dict[str, Any]:
    """Export a campaign's bestiary as portable JSON (drops internal ids/links)."""
    monsters: list[dict[str, Any]] = []
    for monster in session.scalars(
        select(Monster).where(Monster.campaign_id == campaign_id).order_by(Monster.name)
    ):
        block = session.get(StatBlock, monster.stat_block_id)
        if block is None:
            continue
        monsters.append({
            "name": monster.name,
            "rule_system_id": block.rule_system_id,
            "doc": json.loads(block.doc_json),
        })
    return {"kind": "bestiary", "version": 1, "monsters": monsters}


#: Keys the upgrade pass may overwrite rather than only fill in. ``xp`` qualifies because
#: the importer never emitted it — every pre-existing doc has it absent or 0, and nobody
#: hand-authors a 0-XP monster — so a stale value here is always the old bug, not an edit.
_UPGRADE_OVERWRITE_IF_FALSY = ("xp",)

#: Keys always taken from the converter. These come from a source file the GM cannot edit
#: through the app (lair actions and regional effects are joined in from 5etools' separate
#: ``legendarygroups.json``), so there is no local edit for a refresh to overwrite.
_UPGRADE_ALWAYS_REFRESH = ("lair_actions", "regional_effects")


def _actions_are_stale(actions: Any) -> bool:
    """True when an ``actions`` list bears the old converter's signature.

    The previous converter emitted at most one damage part and never a damage ``type``, and
    left the Multiattack entry inline among the real attacks. A hand-authored list does not
    look like that, so this is a safe way to refresh the bulk-imported ones without a
    timestamp to distinguish them by.
    """
    if not isinstance(actions, list) or not actions:
        return False
    has_typed_damage = any(
        part.get("type")
        for action in actions if isinstance(action, dict)
        for part in action.get("damage") or [] if isinstance(part, dict)
    )
    return not has_typed_damage


def upgrade_monster_doc(
    session: Session, system_id: str, monster: Monster, new_doc: dict[str, Any]
) -> bool:
    """Merge freshly converted fields into an existing monster without losing hand edits.

    ``StatBlock`` carries no timestamps, so an edited monster is indistinguishable from a
    freshly imported one. The merge is therefore *additive*: a key is copied only when the
    stored doc lacks it, which preserves GM edits by construction. ``derived_json`` is pure
    plugin output and is always recomputed.

    Returns ``True`` when anything changed.
    """
    block = session.get(StatBlock, monster.stat_block_id)
    if block is None:
        return False
    doc = json.loads(block.doc_json)
    changed = False
    # Attacks written by the old converter carry no damage types and keep Multiattack inline;
    # refreshing them is what turns "1d8+4 damage" back into "1d8+4 slashing plus 4d6 necrotic".
    refresh_actions = "actions" in new_doc and _actions_are_stale(doc.get("actions"))
    for key, value in new_doc.items():
        replaceable = (
            key not in doc
            or key in _UPGRADE_ALWAYS_REFRESH
            or (key in _UPGRADE_OVERWRITE_IF_FALSY and not doc.get(key))
            or (key == "actions" and refresh_actions)
        )
        if replaceable and doc.get(key) != value:
            doc[key] = value
            changed = True

    system = registry.get_system(system_id)
    derived = json.dumps(system.derive("monster", doc))
    if changed or block.derived_json != derived or block.schema_version != system.version:
        block.doc_json = json.dumps(doc)
        block.derived_json = derived
        block.schema_version = system.version
        for facet_key, facet_value in _facets(system_id, doc).items():
            setattr(monster, facet_key, facet_value)
        return True
    return False


def import_monsters_json(
    session: Session,
    campaign_id: str,
    campaign_system_id: str,
    payload: dict[str, Any],
    *,
    mode: str = "create",
) -> dict[str, Any]:
    """Import monsters from a bestiary JSON document. Returns counts + per-entry errors.

    ``mode="upgrade"`` merges into an existing monster of the same name instead of reporting
    it as new — used to backfill fields the converter has since learned to extract. Monsters
    the GM owns (``custom`` source, or any copy-on-write variant) are never touched.
    """
    imported = upgraded = skipped = 0
    errors: list[str] = []
    existing: dict[str, Monster] | None = None
    if mode == "upgrade":
        existing = {
            m.name: m
            for m in session.scalars(select(Monster).where(Monster.campaign_id == campaign_id))
        }

    for i, entry in enumerate(payload.get("monsters", [])):
        name = str(entry.get("name", "")).strip()
        doc = entry.get("doc")
        system_id = entry.get("rule_system_id") or campaign_system_id
        if not name or not isinstance(doc, dict):
            errors.append(f"entry {i}: missing name or doc")
            continue
        if not registry.has_system(system_id):
            errors.append(f"entry {i} ({name}): unknown rule system '{system_id}'")
            continue
        validation = registry.get_system(system_id).validate("monster", doc)
        if validation:
            errors.append(f"entry {i} ({name}): {'; '.join(validation)}")
            continue

        current = existing.get(name) if existing is not None else None
        if current is not None:
            # FR-11.4: the GM's own monsters and variants are theirs, not the importer's.
            if current.source == "custom" or current.variant_of is not None:
                skipped += 1
                continue
            if upgrade_monster_doc(session, system_id, current, doc):
                upgraded += 1
            else:
                skipped += 1
            continue

        _create_monster(session, campaign_id, system_id, name, doc, source="imported")
        imported += 1
    session.commit()
    result = {"imported": imported, "errors": errors}
    if mode == "upgrade":  # keep the create-mode response shape stable for existing callers
        result |= {"upgraded": upgraded, "skipped": skipped}
    return result
