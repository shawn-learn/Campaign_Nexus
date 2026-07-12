"""CalendarMath: anchors, golden fixtures, and round-trip properties (docs/07, §9.8)."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.calendars import GENERIC, HARPTOS
from app.modules.time.calendar import CalendarMath

_GOLDEN = Path(__file__).parent / "fixtures" / "calendar_golden.json"
_CALS = {"generic": CalendarMath(GENERIC), "harptos": CalendarMath(HARPTOS)}


def test_epoch_anchor() -> None:
    gen = CalendarMath(GENERIC)
    f = gen.format(0)
    assert f["label"] == "January 1, 1 CE"
    assert f["weekday"] == "Sunday"
    assert f["time"] == "00:00:00"


def test_time_of_day_seconds() -> None:
    gen = CalendarMath(GENERIC)
    # 14h 30m 15s into day 0.
    secs = 14 * 3600 + 30 * 60 + 15
    assert gen.format(secs)["time"] == "14:30:15"


def test_leap_day_shifts_march() -> None:
    gen = CalendarMath(GENERIC)
    day = gen.seconds_per_day
    # Year 4 is a leap year (Feb has 29 days): Jan(31)+Feb(29) = 60 days precede March 1.
    secs_to_year4 = sum(gen._days_in_year(y) for y in range(1, 4)) * day
    march1 = secs_to_year4 + 60 * day
    parts = gen.to_parts(march1)
    assert parts["year"] == 4
    assert _CALS["generic"].cal["months"][parts["month_index"]]["name"] == "March"
    assert parts["day_of_month"] == 0


def test_harptos_festival_flag() -> None:
    har = CalendarMath(HARPTOS)
    midwinter = har.format(har.seconds_per_day * 30)  # day after Hammer(30)
    assert midwinter["month"] == "Midwinter"
    assert har.to_parts(har.seconds_per_day * 30)["is_festival"] is True


def test_golden_fixtures_match() -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    for case in golden:
        cal = CalendarMath(case["calendar"])  # self-contained: same input as the TS port
        assert cal.to_parts(case["seconds"]) == case["parts"], case
        assert dict(cal.format(case["seconds"])) == case["formatted"], case


def test_roundtrip_and_monotonic_generic() -> None:
    gen = CalendarMath(GENERIC)
    day = gen.seconds_per_day
    prev_key: tuple[int, int, int] | None = None
    for d in range(-800, 800):  # ~4 years each side, crossing leap boundaries
        seconds = d * day + 43525  # 12:05:25 within the day
        p = gen.to_parts(seconds)
        # Reconstruct seconds from parts via the production inverse and assert identity.
        rebuilt = gen.from_parts(
            p["year"], p["month_index"], p["day_of_month"],
            p["hour"], p["minute"], p["second"],
        )
        assert rebuilt == seconds, (seconds, p)
        # Date ordering is monotonic with the clock.
        key = (p["year"], p["day_of_year"], p["hour"] * 3600 + p["minute"] * 60 + p["second"])
        if prev_key is not None:
            assert key > prev_key
        prev_key = key
