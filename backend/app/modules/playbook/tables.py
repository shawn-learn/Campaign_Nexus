"""Random tables (FR-12.x) — a GM roll table that *is* a wiki entity, so a rolled result can
link into the knowledge graph: an encounter to run, an NPC to introduce, or another table to
nest. Two modes, chosen by the ``dice`` field:

* range   — ``dice`` is an ``NdM`` expression; each row has an inclusive ``min``/``max`` and
            the roll lands in exactly one row (the classic d20/d100 table).
* weighted — ``dice`` is ``""``; a row is chosen at random in proportion to its ``weight``.

The dice roll and weighted pick are the only nondeterminism; both funnel through ``roll`` and
accept an injected value so the selection logic is unit-testable without touching ``random``.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

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

_DICE = re.compile(r"^\s*(\d*)d(\d+)\s*$", re.IGNORECASE)


class RandomTableNotFound(LookupError):
    pass


class BadDice(ValueError):
    pass


def parse_dice_terms(dice: str) -> list[tuple[int, int]] | None:
    """Parse an additive dice expression into ``(count, sides)`` terms that are summed on a roll.

    ``"d20"`` → ``[(1, 20)]``; ``"2d6"`` → ``[(2, 6)]``; ``"d12+d8"`` → ``[(1, 12), (1, 8)]``
    (Barovia's 2–20 encounter tables); ``""`` → ``None`` (weighted mode).
    """
    if not dice.strip():
        return None
    terms: list[tuple[int, int]] = []
    for part in dice.split("+"):
        m = _DICE.match(part)
        if not m:
            raise BadDice(dice)
        count = int(m.group(1)) if m.group(1) else 1
        sides = int(m.group(2))
        if count < 1 or sides < 1:
            raise BadDice(dice)
        terms.append((count, sides))
    return terms


def parse_dice(dice: str) -> tuple[int, int] | None:
    """Single-term form: ``"2d6"`` → ``(2, 6)``, ``""`` → ``None``. Rejects multi-term exprs."""
    terms = parse_dice_terms(dice)
    if terms is None:
        return None
    if len(terms) != 1:
        raise BadDice(dice)
    return terms[0]


def _target(session: Session, entity_id: str | None) -> tuple[str | None, str | None]:
    if not entity_id:
        return None, None
    entity = session.get(Entity, entity_id)
    if entity is None:
        return None, None
    return entity.name, entity.entity_type


def _rows_out(session: Session, rows: list[dict[str, Any]]) -> list[TableRowOut]:
    out: list[TableRowOut] = []
    for row in rows:
        name, etype = _target(session, row.get("target_entity_id"))
        out.append(TableRowOut(**row, target_name=name, target_type=etype))
    return out


def to_out(session: Session, table: RandomTable) -> RandomTableOut:
    entity = session.get(Entity, table.entity_id)
    rows = json.loads(table.rows_json)
    return RandomTableOut(
        id=table.entity_id,
        name=entity.name if entity else "",
        dice=table.dice,
        rows=_rows_out(session, rows),
        row_count=len(rows),
    )


def create_random_table(
    session: Session,
    campaign: Campaign,
    *,
    name: str,
    dice: str,
    rows: list[TableRow],
    created_by: str,
) -> RandomTableOut:
    parse_dice_terms(dice)  # validate up front (raises BadDice)
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
    if dice is not None:
        parse_dice_terms(dice)
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
    terms = parse_dice_terms(table.dice)

    rolled: int | None = None
    if terms is not None:
        rolled = forced_roll if forced_roll is not None else sum(
            random.randint(1, sides) for count, sides in terms for _ in range(count)
        )
        index = select_range(rows, rolled)
    else:
        index = select_weighted(rows, random.random()) if rows else None

    if index is None:
        return RollOut(roll=rolled, index=None, text="(no matching row)")
    row = rows[index]
    name, etype = _target(session, row.get("target_entity_id"))
    return RollOut(
        roll=rolled, index=index, text=str(row.get("text", "")),
        target_entity_id=row.get("target_entity_id"), target_name=name, target_type=etype,
    )
