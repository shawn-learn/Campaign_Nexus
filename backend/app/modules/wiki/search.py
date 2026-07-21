"""Full-text search over entities via SQLite FTS5 (ADR-002, NFR-1.2: <100 ms).

Design notes:
- A single FTS5 table indexes name/summary/article_text/tags; entity_id and campaign_id
  are UNINDEXED columns carried for filtering. An ``entity_fts_map`` gives each entity a
  stable integer rowid so updates/deletes are O(1).
- The index is maintained by the entity service inside the same transaction as the
  mutation (contentless-style discipline), so it never drifts from the registry.
- SQLite-specific SQL is isolated here (NFR-5.2): a PostgreSQL port swaps this module for
  a tsvector/GIN implementation behind the same function signatures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.wiki.models import Entity, EntityTag, Tag

# bm25 weights, one per FTS column: entity_id, campaign_id, name, summary, article, tags.
# Name matches dominate; summary and tags matter; article body is lightest (R-11 tuning).
_BM25_WEIGHTS = "0.0, 0.0, 10.0, 4.0, 1.0, 3.0"

_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


def ensure_search_schema(session: Session) -> None:
    """Idempotently create the FTS table and rowid map (safe to call at startup/tests)."""
    session.execute(
        text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5("
            "  entity_id UNINDEXED, campaign_id UNINDEXED,"
            "  name, summary, article_text, tags,"
            "  tokenize='unicode61 remove_diacritics 2')"
        )
    )
    session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS entity_fts_map("
            "  entity_id TEXT PRIMARY KEY, rowid INTEGER NOT NULL)"
        )
    )


def _tags_text(session: Session, entity_id: str) -> str:
    names = session.scalars(
        select(Tag.name)
        .join(EntityTag, EntityTag.tag_id == Tag.id)
        .where(EntityTag.entity_id == entity_id)
    )
    return " ".join(names)


def _rowid_for(session: Session, entity_id: str) -> int | None:
    return session.execute(
        text("SELECT rowid FROM entity_fts_map WHERE entity_id = :eid"),
        {"eid": entity_id},
    ).scalar_one_or_none()


def remove_entity(session: Session, entity_id: str) -> None:
    rowid = _rowid_for(session, entity_id)
    if rowid is None:
        return
    session.execute(text("DELETE FROM entity_fts WHERE rowid = :r"), {"r": rowid})
    session.execute(text("DELETE FROM entity_fts_map WHERE entity_id = :eid"), {"eid": entity_id})


def reindex(session: Session, entity: Entity) -> None:
    """Upsert an entity into the index; drop it when soft-deleted (so search hides it)."""
    if entity.deleted_at_real is not None:
        remove_entity(session, entity.id)
        return

    params = {
        "eid": entity.id,
        "cid": entity.campaign_id,
        "name": entity.name,
        "summary": entity.summary or "",
        "article": entity.article_text or "",
        "tags": _tags_text(session, entity.id),
    }
    rowid = _rowid_for(session, entity.id)
    if rowid is not None:
        session.execute(text("DELETE FROM entity_fts WHERE rowid = :r"), {"r": rowid})
        session.execute(
            text(
                "INSERT INTO entity_fts(rowid, entity_id, campaign_id, name, summary,"
                " article_text, tags) VALUES(:r, :eid, :cid, :name, :summary, :article, :tags)"
            ),
            {"r": rowid, **params},
        )
    else:
        session.execute(
            text(
                "INSERT INTO entity_fts(entity_id, campaign_id, name, summary, article_text,"
                " tags) VALUES(:eid, :cid, :name, :summary, :article, :tags)"
            ),
            params,
        )
        new_rowid = session.execute(text("SELECT last_insert_rowid()")).scalar_one()
        session.execute(
            text("INSERT INTO entity_fts_map(entity_id, rowid) VALUES(:eid, :r)"),
            {"eid": entity.id, "r": new_rowid},
        )


# Columns the deep search restricts to when scope='prose': body text, not the name.
_PROSE_COLUMNS = "{summary article_text}"


def _match_query(raw: str, *, columns: str | None = None) -> str | None:
    """Turn user input into a safe FTS5 MATCH expression with prefix search-as-you-type.

    ``columns`` optionally restricts the match to an FTS5 column filter set, so a caller
    can ask "where is this mentioned in the prose?" rather than "what is this named?".
    """
    tokens = [t for t in _TOKEN.split(raw.strip()) if t]
    if not tokens:
        return None
    # Quote each token (defuses FTS operators) and add a prefix wildcard.
    expr = " ".join(f'"{t}"*' for t in tokens)
    if columns:
        # Column filters bind tighter than AND, so the token list needs parentheses.
        return f"{columns} : ({expr})"
    return expr


def search_entity_ids(
    session: Session,
    campaign_id: str,
    raw_query: str,
    *,
    entity_type: str | None = None,
    tag_id: str | None = None,
    limit: int = 20,
) -> list[str]:
    match = _match_query(raw_query)
    if match is None:
        return []

    sql = (
        f"SELECT f.entity_id AS entity_id, bm25(entity_fts, {_BM25_WEIGHTS}) AS rank "
        "FROM entity_fts f JOIN entity e ON e.id = f.entity_id "
        "WHERE entity_fts MATCH :q AND f.campaign_id = :cid AND e.deleted_at_real IS NULL"
    )
    params: dict[str, object] = {"q": match, "cid": campaign_id, "lim": limit}
    if entity_type:
        sql += " AND e.entity_type = :etype"
        params["etype"] = entity_type
    if tag_id:
        sql += " AND EXISTS (SELECT 1 FROM entity_tag et WHERE et.entity_id = e.id"
        sql += " AND et.tag_id = :tag_id)"
        params["tag_id"] = tag_id
    sql += " ORDER BY rank LIMIT :lim"

    rows = session.execute(text(sql), params).all()
    return [row.entity_id for row in rows]


# Snippet column indexes, matching the FTS5 column order declared above.
_COL_SUMMARY = 3
_COL_ARTICLE = 4

# snippet() markup. The frontend renders these as highlights; it escapes everything else,
# so the tags must be a pair it recognises rather than arbitrary HTML from the document.
_MARK_OPEN = "[[hl]]"
_MARK_CLOSE = "[[/hl]]"
_ELLIPSIS = "…"


@dataclass(frozen=True)
class SearchHit:
    """One ranked match, with the prose context that caused it."""

    entity_id: str
    rank: float
    summary_snippet: str | None
    article_snippet: str | None


def search_entity_hits(
    session: Session,
    campaign_id: str,
    raw_query: str,
    *,
    entity_type: str | None = None,
    tag_id: str | None = None,
    prose_only: bool = False,
    limit: int = 20,
) -> list[SearchHit]:
    """Ranked search that also returns highlighted snippets of the matching prose.

    ``prose_only`` restricts matching to summary/article body — the "where did I write
    about this?" question, as opposed to the name-weighted lookup ``search_entity_ids``
    does for the command palette.
    """
    match = _match_query(raw_query, columns=_PROSE_COLUMNS if prose_only else None)
    if match is None:
        return []

    def _snip(col: int, tokens: int) -> str:
        return (
            f"snippet(entity_fts, {col}, '{_MARK_OPEN}', '{_MARK_CLOSE}',"
            f" '{_ELLIPSIS}', {tokens})"
        )

    sql = (
        "SELECT f.entity_id AS entity_id, "
        f"bm25(entity_fts, {_BM25_WEIGHTS}) AS rank, "
        f"{_snip(_COL_SUMMARY, 20)} AS summary_snippet, "
        f"{_snip(_COL_ARTICLE, 32)} AS article_snippet "
        "FROM entity_fts f JOIN entity e ON e.id = f.entity_id "
        "WHERE entity_fts MATCH :q AND f.campaign_id = :cid AND e.deleted_at_real IS NULL"
    )
    params: dict[str, object] = {"q": match, "cid": campaign_id, "lim": limit}
    if entity_type:
        sql += " AND e.entity_type = :etype"
        params["etype"] = entity_type
    if tag_id:
        sql += " AND EXISTS (SELECT 1 FROM entity_tag et WHERE et.entity_id = e.id"
        sql += " AND et.tag_id = :tag_id)"
        params["tag_id"] = tag_id
    sql += " ORDER BY rank LIMIT :lim"

    def _clean(value: str | None) -> str | None:
        # snippet() returns the whole (short) column when nothing in it matched; only the
        # ones carrying a highlight are worth showing as evidence.
        if not value or _MARK_OPEN not in value:
            return None
        return value

    return [
        SearchHit(
            entity_id=row.entity_id,
            rank=row.rank,
            summary_snippet=_clean(row.summary_snippet),
            article_snippet=_clean(row.article_snippet),
        )
        for row in session.execute(text(sql), params).all()
    ]
