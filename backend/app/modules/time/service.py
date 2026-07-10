"""Time engine service. ``advance_time`` is the clock's discrete writer (docs/07, §9.3).

The clock is stored in seconds. Three things move it:
- discrete jumps (manual / rest / travel / scheduled events) via ``advance_time``;
- real-time ticking (``settle_realtime``): while enabled and not paused, wall-clock seconds
  accrue into the clock;
- combat, which pauses real time and drives the clock at the round length (6s).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.calendars import DEFAULT_CALENDAR
from app.core.clock import now_real, now_real_iso
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.time import scheduled
from app.modules.time.calendar import CalendarMath
from app.modules.time.schemas import (
    AdvancePreview,
    AdvanceReport,
    ClockFormatted,
    ClockOut,
)


class NoAdvance(ValueError):
    pass


def calendar_for(campaign: Campaign) -> CalendarMath:
    raw: dict[str, Any]
    try:
        raw = json.loads(campaign.calendar_json) if campaign.calendar_json else {}
    except json.JSONDecodeError:
        raw = {}
    return CalendarMath(raw or DEFAULT_CALENDAR)


def _formatted(cal: CalendarMath, seconds: int) -> ClockFormatted:
    return ClockFormatted(**cal.format(seconds))


def _elapsed_real_seconds(anchor_iso: str) -> int:
    try:
        anchor = datetime.fromisoformat(anchor_iso)
    except ValueError:
        return 0
    return max(0, int((now_real() - anchor).total_seconds()))


def settle_realtime(session: Session, campaign: Campaign) -> None:
    """Fold accrued wall-clock seconds into the persisted clock and re-anchor.

    No-op while paused (combat) or disabled. Called before any operation that needs an
    authoritative clock base (reads, advances, combat start), so real time is never lost.
    """
    if not campaign.realtime_enabled or campaign.realtime_paused:
        return
    if campaign.realtime_anchor_real is None:
        campaign.realtime_anchor_real = now_real_iso()
        session.commit()
        return
    elapsed = _elapsed_real_seconds(campaign.realtime_anchor_real)
    if elapsed > 0:
        campaign.clock_time_game += elapsed
        campaign.realtime_anchor_real = now_real_iso()
        session.commit()


def set_realtime(session: Session, campaign: Campaign, enabled: bool) -> ClockOut:
    if enabled and not campaign.realtime_enabled:
        campaign.realtime_enabled = True
        campaign.realtime_anchor_real = now_real_iso()
    elif not enabled and campaign.realtime_enabled:
        settle_realtime(session, campaign)  # bank the elapsed time first
        campaign.realtime_enabled = False
        campaign.realtime_anchor_real = None
    session.commit()
    return get_clock(campaign)


def get_clock(campaign: Campaign) -> ClockOut:
    cal = calendar_for(campaign)
    return ClockOut(
        time_game=campaign.clock_time_game,
        calendar_name=str(cal.cal.get("name", "Calendar")),
        calendar=cal.cal,
        realtime_enabled=bool(campaign.realtime_enabled),
        realtime_paused=bool(campaign.realtime_paused),
        formatted=_formatted(cal, campaign.clock_time_game),
    )


def read_clock(session: Session, campaign: Campaign) -> ClockOut:
    """Clock read that first banks any real-time progression (so it visibly ticks)."""
    settle_realtime(session, campaign)
    return get_clock(campaign)


def advance_time(
    session: Session,
    campaign: Campaign,
    *,
    delta_seconds: int,
    reason: str,
) -> AdvanceReport:
    """Advance the clock forward by ``delta_seconds`` and record ``time_advanced``."""
    if delta_seconds <= 0:
        raise NoAdvance("advancement must be a positive amount of time")

    settle_realtime(session, campaign)  # bank real time before the discrete jump
    cal = calendar_for(campaign)
    from_time = campaign.clock_time_game
    to_time = from_time + delta_seconds

    with command_tx(session, campaign.id, actor="time_engine") as ctx:
        # Fire due scheduled events in order, letting the clock flow through them (§9.3),
        # then land on the target time — all in one transaction (FR-5.6).
        fired = scheduled.fire_due_events(session, ctx, cal, campaign, to_time)
        campaign.clock_time_game = to_time
        label = cal.format(to_time)["label"]
        ctx.emit(
            "time_advanced",
            payload={"from": from_time, "to": to_time, "reason": reason},
            narrative=f"Time advanced to {label} ({reason}).",
            occurred_at_game=to_time,
        )

    return AdvanceReport(
        from_time=from_time,
        to_time=to_time,
        reason=reason,
        formatted=_formatted(cal, to_time),
        fired=fired,
    )


def preview_advance(
    session: Session, campaign: Campaign, *, delta_seconds: int
) -> AdvancePreview:
    """Dry run: what would fire between now and now+delta, without committing (§9.5)."""
    cal = calendar_for(campaign)
    from_time = campaign.clock_time_game
    to_time = from_time + delta_seconds
    return AdvancePreview(
        from_time=from_time,
        to_time=to_time,
        would_fire=scheduled.preview_due_events(session, cal, campaign, to_time),
    )
