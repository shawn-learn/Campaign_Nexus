"""Rules service: validate/derive documents and persist stat blocks.

Stat blocks are reference data (character/monster definitions), not world history, so they
are written directly rather than through the event pipeline. The plugin is the sole
authority on a document's shape (validate) and computed values (derive).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.rules import registry
from app.modules.rules.interface import UnknownSheetType
from app.modules.rules.models import Monster, StatBlock


class ValidationFailed(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class StatBlockNotFound(LookupError):
    pass


def validate_and_derive(
    rule_system_id: str, sheet_type: str, doc: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    system = registry.get_system(rule_system_id)  # raises UnknownRuleSystem
    try:
        errors = system.validate(sheet_type, doc)
    except UnknownSheetType as exc:
        return [f"unknown sheet_type: {exc}"], {}
    derived = system.derive(sheet_type, doc) if not errors else {}
    return errors, derived


def _to_out_fields(block: StatBlock) -> dict[str, Any]:
    return {
        "id": block.id,
        "campaign_id": block.campaign_id,
        "rule_system_id": block.rule_system_id,
        "sheet_type": block.sheet_type,
        "schema_version": block.schema_version,
        "label": block.label,
        "doc": json.loads(block.doc_json),
        "derived": json.loads(block.derived_json),
    }


def list_stat_blocks(
    session: Session,
    campaign_id: str,
    *,
    sheet_type: str | None = None,
    rule_system_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(StatBlock).where(StatBlock.campaign_id == campaign_id)
    if sheet_type:
        stmt = stmt.where(StatBlock.sheet_type == sheet_type)
    if rule_system_id:
        stmt = stmt.where(StatBlock.rule_system_id == rule_system_id)
    return [_to_out_fields(b) for b in session.scalars(stmt.order_by(StatBlock.label))]


def get_stat_block(session: Session, campaign_id: str, block_id: str) -> dict[str, Any]:
    block = session.get(StatBlock, block_id)
    if block is None or block.campaign_id != campaign_id:
        raise StatBlockNotFound(block_id)
    return _to_out_fields(block)


def create_stat_block(
    session: Session,
    campaign_id: str,
    *,
    rule_system_id: str,
    sheet_type: str,
    label: str,
    doc: dict[str, Any],
) -> dict[str, Any]:
    system = registry.get_system(rule_system_id)
    errors, derived = validate_and_derive(rule_system_id, sheet_type, doc)
    if errors:
        raise ValidationFailed(errors)
    block = StatBlock(
        id=new_id(),
        campaign_id=campaign_id,
        rule_system_id=rule_system_id,
        sheet_type=sheet_type,
        schema_version=system.version,
        label=label,
        doc_json=json.dumps(doc),
        derived_json=json.dumps(derived),
    )
    session.add(block)
    session.commit()
    return _to_out_fields(block)


def update_stat_block(
    session: Session,
    campaign_id: str,
    block_id: str,
    *,
    label: str | None,
    doc: dict[str, Any],
) -> dict[str, Any]:
    block = session.get(StatBlock, block_id)
    if block is None or block.campaign_id != campaign_id:
        raise StatBlockNotFound(block_id)
    errors, derived = validate_and_derive(block.rule_system_id, block.sheet_type, doc)
    if errors:
        raise ValidationFailed(errors)
    if label is not None:
        block.label = label
    block.doc_json = json.dumps(doc)
    block.derived_json = json.dumps(derived)
    block.schema_version = registry.get_system(block.rule_system_id).version
    if block.sheet_type == "monster":
        _resync_monster(session, block, doc)
    session.commit()
    return _to_out_fields(block)


def _resync_monster(session: Session, block: StatBlock, doc: dict[str, Any]) -> None:
    """Keep the ``monster`` row in step with an edit to its stat block.

    Editing a monster goes through the stat-block PUT, but a monster's *name* (the label) and
    its *facet columns* (CR, type, …) also live on the ``monster`` row, which drives the
    bestiary list and its filters. Without this, renaming a monster or changing its CR left the
    list showing the stale value until the next import.
    """
    monster = session.scalar(select(Monster).where(Monster.stat_block_id == block.id))
    if monster is None:
        return
    monster.name = block.label
    values = registry.get_system(block.rule_system_id).monster_facets(doc)
    for key in ("facet1_num", "facet2_num", "facet1_text", "facet2_text"):
        setattr(monster, key, values.get(key))
