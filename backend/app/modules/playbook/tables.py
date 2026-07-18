"""Random tables (FR-12.x) — a GM roll table that *is* a wiki entity, so a rolled result can
link into the knowledge graph: an encounter to run, an NPC to introduce, or another table to
nest. Two modes, chosen by the ``dice`` field:

* range   — ``dice`` is a dice expression (``1d20``, ``d12+d8``, ``2d6+3``); each row has an
            inclusive ``min``/``max`` and the roll lands in exactly one row.
* weighted — ``dice`` is ``""``; a row is chosen at random in proportion to its ``weight``.

Notation is parsed and rolled by ``app.core.dice`` — the one dice grammar in the codebase.
Only the ``""`` weighted sentinel is table-specific, so it lives here rather than there.

The dice roll and weighted pick are the only nondeterminism; both funnel through ``roll`` and
accept an injected value so the selection logic is unit-testable without touching ``random``.
"""

from __future__ import annotations

import json
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import dice as core_dice
from app.modules.campaign.models import Campaign
from app.modules.playbook.models import RandomTable
from app.modules.playbook.schemas import (
    RandomTableOut,
    RollOut,
    TableRow,
    TableRowOut,
)
from app.modules.wiki import search as wiki_search
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate, EntityUpdate


class RandomTableNotFound(LookupError):
    pass


class BadDice(ValueError):
    pass


class InvalidTable(ValueError):
    pass


def dice_spec(dice: str) -> str | None:
    """Validate a table's ``dice`` field: ``""`` → ``None`` (weighted), else the expression.

    Re-raises the core parser's error as ``BadDice`` so the router's 422 mapping still fires;
    a leaked ``BadExpression`` would surface as a 500 instead.
    """
    expr = dice.strip()
    if not expr:
        return None
    try:
        core_dice.parse(expr)
    except core_dice.BadExpression as exc:
        raise BadDice(dice) from exc
    return expr


def _target(
    session: Session, campaign_id: str, entity_id: str | None
) -> tuple[str | None, str | None]:
    if not entity_id:
        return None, None
    entity = session.get(Entity, entity_id)
    if entity is None or entity.campaign_id != campaign_id or entity.deleted_at_real is not None:
        return None, None
    return entity.name, entity.entity_type


def _rows_out(
    session: Session, campaign_id: str, rows: list[dict[str, Any]]
) -> list[TableRowOut]:
    out: list[TableRowOut] = []
    for row in rows:
        name, etype = _target(session, campaign_id, row.get("target_entity_id"))
        out.append(TableRowOut(**row, target_name=name, target_type=etype))
    return out


def to_out(session: Session, table: RandomTable) -> RandomTableOut:
    entity = session.get(Entity, table.entity_id)
    rows = json.loads(table.rows_json)
    return RandomTableOut(
        id=table.entity_id,
        name=entity.name if entity else "",
        dice=table.dice,
        rows=_rows_out(session, table.campaign_id, rows),
        row_count=len(rows),
    )


def validate_rows(session: Session, campaign_id: str, dice: str, rows: list[TableRow]) -> None:
    """Reject tables that cannot produce an unambiguous, campaign-safe result."""
    spec = dice_spec(dice)  # bad notation fails before the row checks, as it always has
    if not rows:
        raise InvalidTable("a random table needs at least one row")

    for row in rows:
        if not row.text.strip() and row.target_entity_id is None:
            raise InvalidTable("each row needs result text or a linked entity")
        if row.target_entity_id is not None:
            target = session.get(Entity, row.target_entity_id)
            if (
                target is None
                or target.campaign_id != campaign_id
                or target.deleted_at_real is not None
            ):
                raise InvalidTable("row target must be an active entity in this campaign")

    if spec is None:
        return

    minimum, maximum = core_dice.bounds(spec)
    ranges: list[tuple[int, int]] = []
    for row in rows:
        if row.min is None or row.max is None:
            raise InvalidTable("dice tables require a min and max for every row")
        if row.min > row.max:
            raise InvalidTable("a row minimum cannot exceed its maximum")
        if row.min < minimum or row.max > maximum:
            raise InvalidTable(f"row ranges must stay within {minimum} to {maximum}")
        ranges.append((row.min, row.max))
    ranges.sort()
    expected = minimum
    for lo, hi in ranges:
        if lo != expected:
            raise InvalidTable("row ranges must cover every possible roll exactly once")
        expected = hi + 1
    if expected != maximum + 1:
        raise InvalidTable("row ranges must cover every possible roll exactly once")


def create_random_table(
    session: Session,
    campaign: Campaign,
    *,
    name: str,
    dice: str,
    rows: list[TableRow],
    created_by: str,
) -> RandomTableOut:
    validate_rows(session, campaign.id, dice, rows)
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="random_table", name=name), created_by=created_by,
    )
    table = RandomTable(
        entity_id=entity.id, campaign_id=campaign.id, dice=dice,
        rows_json=json.dumps([r.model_dump() for r in rows]),
    )
    session.add(table)
    session.commit()
    return to_out(session, table)


def _require(session: Session, campaign_id: str, table_id: str) -> RandomTable:
    table = session.get(RandomTable, table_id)
    if table is None or table.campaign_id != campaign_id:
        raise RandomTableNotFound(table_id)
    return table


def get_random_table(session: Session, campaign: Campaign, table_id: str) -> RandomTableOut:
    return to_out(session, _require(session, campaign.id, table_id))


def list_random_tables(session: Session, campaign: Campaign) -> list[RandomTableOut]:
    rows = session.scalars(
        select(RandomTable).where(RandomTable.campaign_id == campaign.id)
    )
    return [to_out(session, t) for t in rows]


def update_random_table(
    session: Session,
    campaign: Campaign,
    table_id: str,
    *,
    name: str | None = None,
    dice: str | None,
    rows: list[TableRow] | None,
) -> RandomTableOut:
    table = _require(session, campaign.id, table_id)
    next_dice = dice if dice is not None else table.dice
    next_rows = rows
    if next_rows is None:
        next_rows = [TableRow(**row) for row in json.loads(table.rows_json)]
    validate_rows(session, campaign.id, next_dice, next_rows)
    if dice is not None:
        table.dice = dice
    if rows is not None:
        table.rows_json = json.dumps([r.model_dump() for r in rows])
    if name is not None:
        # The display name lives on the backing wiki entity (keeps the graph in sync).
        wiki_service.update_entity(
            session, campaign.id, table.entity_id, data=EntityUpdate(name=name)
        )
    session.commit()
    return to_out(session, table)


def delete_random_table(session: Session, campaign: Campaign, table_id: str) -> None:
    """Fully remove a table: the RandomTable row and its backing wiki entity.

    Deleting the entity cascades to its links and tags (FK ON DELETE CASCADE); we also drop
    it from the full-text index. This is a hard delete, unlike the soft-delete used for
    ordinary lore entities — a roll table is a tool, not campaign history.
    """
    table = _require(session, campaign.id, table_id)
    entity = session.get(Entity, table.entity_id)
    session.delete(table)
    if entity is not None:
        wiki_search.remove_entity(session, entity.id)
        session.delete(entity)
    session.commit()


# --------------------------------------------------------------------------- #
# Rolling — the only nondeterminism, isolated and injectable for tests.
# --------------------------------------------------------------------------- #
def select_range(rows: list[dict[str, Any]], roll: int) -> int | None:
    """Index of the row whose inclusive [min, max] contains ``roll`` (first match)."""
    for i, row in enumerate(rows):
        lo, hi = row.get("min"), row.get("max")
        if lo is None or hi is None:
            continue
        if int(lo) <= roll <= int(hi):
            return i
    return None


def select_weighted(rows: list[dict[str, Any]], pick: float) -> int | None:
    """Index chosen by ``pick`` ∈ [0, 1) against cumulative weights (weight defaults to 1)."""
    weights = [max(1, int(r.get("weight") or 1)) for r in rows]
    total = sum(weights)
    if total <= 0:
        return None
    target = pick * total
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if target < cumulative:
            return i
    return len(rows) - 1


def roll(
    session: Session,
    campaign: Campaign,
    table_id: str,
    *,
    forced_roll: int | None = None,
) -> RollOut:
    table = _require(session, campaign.id, table_id)
    rows: list[dict[str, Any]] = json.loads(table.rows_json)
    spec = dice_spec(table.dice)

    rolled: int | None = None
    if spec is not None:
        rolled = forced_roll if forced_roll is not None else core_dice.roll(spec).total
        index = select_range(rows, rolled)
    else:
        index = select_weighted(rows, random.random()) if rows else None

    if index is None:
        return RollOut(roll=rolled, index=None, text="(no matching row)")
    row = rows[index]
    name, etype = _target(session, campaign.id, row.get("target_entity_id"))
    return RollOut(
        roll=rolled, index=index, text=str(row.get("text", "")),
        target_entity_id=row.get("target_entity_id"), target_name=name, target_type=etype,
    )
