"""Chronicle service: timeline, sessions, and quick notes (docs/04, §6.4)."""

from __future__ import annotations

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session as DbSession

from app.core.clock import now_real_iso
from app.core.domain_event import DomainEvent
from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.chronicle.models import Session, TimelineEntity, TimelineEntry


class SessionError(ValueError):
    pass


class NotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
def query_timeline(
    db: DbSession,
    campaign_id: str,
    *,
    session_id: str | None = None,
    entity_id: str | None = None,
    from_game: int | None = None,
    to_game: int | None = None,
    significance_min: int | None = None,
    include_hidden: bool = False,
    limit: int = 200,
) -> list[TimelineEntry]:
    stmt = select(TimelineEntry).where(TimelineEntry.campaign_id == campaign_id)
    if not include_hidden:
        stmt = stmt.where(TimelineEntry.is_hidden == False)  # noqa: E712
    if session_id:
        stmt = stmt.where(TimelineEntry.session_id == session_id)
    if from_game is not None:
        stmt = stmt.where(TimelineEntry.occurred_at_game >= from_game)
    if to_game is not None:
        stmt = stmt.where(TimelineEntry.occurred_at_game <= to_game)
    if significance_min is not None:
        stmt = stmt.where(TimelineEntry.significance >= significance_min)
    if entity_id:
        stmt = stmt.join(TimelineEntity, TimelineEntity.timeline_id == TimelineEntry.id).where(
            TimelineEntity.entity_id == entity_id
        )
    stmt = stmt.order_by(TimelineEntry.occurred_at_game.desc(), TimelineEntry.id.desc())
    return list(db.scalars(stmt.limit(limit)))


def create_manual_entry(
    db: DbSession,
    campaign_id: str,
    *,
    title: str,
    body: str | None,
    occurred_at_game: int,
    icon: str | None,
    significance: int,
    entity_ids: list[str],
) -> TimelineEntry:
    """GM-authored lore (event_id NULL). Curation, so it writes directly (not an event)."""
    entry = TimelineEntry(
        id=new_id(),
        campaign_id=campaign_id,
        event_id=None,
        occurred_at_game=occurred_at_game,
        title=title,
        body=body,
        icon=icon or "✎",
        significance=significance,
    )
    db.add(entry)
    db.flush()
    for entity_id in entity_ids:
        db.add(TimelineEntity(timeline_id=entry.id, entity_id=entity_id))
    db.commit()
    return entry


def clear_timeline(db: DbSession, campaign_id: str) -> None:
    """Delete *all* timeline entries for the campaign — projected entries AND manual lore.

    A full wipe (unlike ``projectors.reset_timeline``, which keeps lore for a replay). Does
    not touch the immutable event log; a subsequent projection rebuild would repopulate the
    projected entries.
    """
    ids = list(
        db.scalars(select(TimelineEntry.id).where(TimelineEntry.campaign_id == campaign_id))
    )
    if not ids:
        return
    db.execute(delete(TimelineEntity).where(TimelineEntity.timeline_id.in_(ids)))
    db.execute(delete(TimelineEntry).where(TimelineEntry.id.in_(ids)))
    db.commit()


def set_hidden(db: DbSession, campaign_id: str, entry_id: str, hidden: bool) -> TimelineEntry:
    entry = db.get(TimelineEntry, entry_id)
    if entry is None or entry.campaign_id != campaign_id:
        raise NotFound(entry_id)
    entry.is_hidden = hidden
    db.commit()
    return entry


def delete_manual_entry(db: DbSession, campaign_id: str, entry_id: str) -> None:
    """Delete a single GM-authored lore entry.

    Only manual lore (``event_id`` NULL) may be deleted: projected entries mirror the
    immutable event log and would simply reappear on the next projection rebuild, so those
    are hidden (``set_hidden``) rather than deleted.
    """
    entry = db.get(TimelineEntry, entry_id)
    if entry is None or entry.campaign_id != campaign_id:
        raise NotFound(entry_id)
    if entry.event_id is not None:
        raise SessionError("only manual lore entries can be deleted; hide projected events instead")
    db.execute(delete(TimelineEntity).where(TimelineEntity.timeline_id == entry_id))
    db.delete(entry)
    db.commit()


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def list_sessions(db: DbSession, campaign_id: str) -> list[Session]:
    return list(
        db.scalars(
            select(Session)
            .where(Session.campaign_id == campaign_id)
            .order_by(Session.session_number)
        )
    )


def _require_session(db: DbSession, campaign_id: str, session_id: str) -> Session:
    sess = db.get(Session, session_id)
    if sess is None or sess.campaign_id != campaign_id:
        raise NotFound(session_id)
    return sess


def create_session(
    db: DbSession, campaign_id: str, *, real_date: str | None, summary: str | None
) -> Session:
    next_number = (
        db.scalar(
            select(func.coalesce(func.max(Session.session_number), 0)).where(
                Session.campaign_id == campaign_id
            )
        )
        or 0
    ) + 1
    sess = Session(
        id=new_id(),
        campaign_id=campaign_id,
        session_number=next_number,
        real_date=real_date or now_real_iso(),
        status="planned",
        summary=summary,
    )
    db.add(sess)
    db.commit()
    return sess


def start_session(db: DbSession, campaign_id: str, session_id: str) -> Session:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFound(campaign_id)
    if campaign.current_session_id is not None and campaign.current_session_id != session_id:
        raise SessionError("another session is already live")
    sess = _require_session(db, campaign_id, session_id)
    if sess.status == "completed":
        raise SessionError("session already completed")

    with command_tx(db, campaign_id, actor="gm") as ctx:
        campaign.current_session_id = session_id
        sess.status = "live"
        sess.clock_start_game = campaign.clock_time_game
        ctx.emit(
            "session_started",
            payload={"session_number": sess.session_number},
            narrative=f"Session {sess.session_number} started.",
            session_id=session_id,
        )
    db.refresh(sess)
    # A live session is about to churn the data; snapshot the pre-session state (FR-13.2).
    # Best-effort — a backup hiccup must not abort starting the game.
    try:
        from app.backup import service as backup_service

        backup_service.create_backup(db, reason="session-start")
    except Exception:  # pragma: no cover - non-fatal
        pass
    return sess


def end_session(db: DbSession, campaign_id: str, session_id: str) -> Session:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFound(campaign_id)
    sess = _require_session(db, campaign_id, session_id)
    if sess.status != "live":
        raise SessionError("session is not live")

    with command_tx(db, campaign_id, actor="gm") as ctx:
        campaign.current_session_id = None
        sess.status = "completed"
        sess.clock_end_game = campaign.clock_time_game
        ctx.emit(
            "session_ended",
            payload={"session_number": sess.session_number},
            narrative=f"Session {sess.session_number} ended.",
            session_id=session_id,  # explicit: current_session_id was just cleared
        )
    db.refresh(sess)
    return sess


def session_events(db: DbSession, session_id: str) -> list[DomainEvent]:
    return list(
        db.scalars(
            select(DomainEvent)
            .where(DomainEvent.session_id == session_id)
            .order_by(DomainEvent.seq)
        )
    )


def session_entities(db: DbSession, session_id: str) -> list[dict[str, str]]:
    """Distinct entities referenced by this session's events (auto-links, FR-9.3)."""
    rows = db.execute(
        text(
            "SELECT DISTINCT e.id, e.name, e.entity_type "
            "FROM domain_event de "
            "JOIN json_each(de.subject_entity_ids_json) je "
            "JOIN entity e ON e.id = je.value "
            "WHERE de.session_id = :sid "
            "ORDER BY e.name"
        ),
        {"sid": session_id},
    ).all()
    return [{"entity_id": r[0], "name": r[1], "entity_type": r[2]} for r in rows]


# --------------------------------------------------------------------------- #
# Quick notes
# --------------------------------------------------------------------------- #
def capture_note(
    db: DbSession, campaign_id: str, text_body: str, entity_ids: list[str]
) -> None:
    """Append a note; auto-stamped with the live session by the pipeline (FR-9.4)."""
    with command_tx(db, campaign_id, actor="gm") as ctx:
        ctx.emit(
            "note_captured",
            payload={"text": text_body},
            narrative=text_body,
            subject_entity_ids=tuple(entity_ids),
        )
