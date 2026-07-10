"""Calendar preset *data* (docs/07-time-engine.md, §9.1).

Kept in core (a leaf) so both the campaign module (which stamps a calendar onto new
campaigns) and the time module (whose CalendarMath interprets it) can use it without
crossing module boundaries. The math itself lives in ``app.modules.time.calendar``.

Model (deliberately simplified from the doc for the MVP; golden tests lock the behavior):
- ``months``: ordered list of ``{name, days, festival?}``. ``festival`` months are flavor
  only in v1 (they still advance the weekday); true out-of-week days are post-MVP.
- ``leap``: ``{every_years, month_index, extra_days}`` adds days to one month in leap years.
- ``weekdays``: names cycled by absolute day index.
- ``seasons``: ``{name, start_month_index}`` ranges.
- ``start_year``: the year label at clock minute 0.
"""

from __future__ import annotations

from typing import Any

GENERIC: dict[str, Any] = {
    "id": "generic",
    "name": "Generic Fantasy Calendar",
    "epoch_label": "CE",
    "start_year": 1,
    "seconds_per_minute": 60,
    "minutes_per_hour": 60,
    "hours_per_day": 24,
    "weekdays": [
        "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    ],
    "months": [
        {"name": "January", "days": 31},
        {"name": "February", "days": 28},
        {"name": "March", "days": 31},
        {"name": "April", "days": 30},
        {"name": "May", "days": 31},
        {"name": "June", "days": 30},
        {"name": "July", "days": 31},
        {"name": "August", "days": 31},
        {"name": "September", "days": 30},
        {"name": "October", "days": 31},
        {"name": "November", "days": 30},
        {"name": "December", "days": 31},
    ],
    "leap": {"every_years": 4, "month_index": 1, "extra_days": 1},  # Feb +1 every 4 years
    "seasons": [
        {"name": "Winter", "start_month_index": 11},
        {"name": "Spring", "start_month_index": 2},
        {"name": "Summer", "start_month_index": 5},
        {"name": "Autumn", "start_month_index": 8},
    ],
}

# Forgotten-Realms-flavored calendar: 12 months of 30 days + 5 festival days, 10-day
# tendays, and a leap day (Shieldmeet) folded into Midsummer every 4 years.
HARPTOS: dict[str, Any] = {
    "id": "harptos",
    "name": "Calendar of Harptos",
    "epoch_label": "DR",
    "start_year": 1372,
    "seconds_per_minute": 60,
    "minutes_per_hour": 60,
    "hours_per_day": 24,
    "weekdays": [f"{n} day" for n in range(1, 11)],  # a 10-day tenday
    "months": [
        {"name": "Hammer", "days": 30},
        {"name": "Midwinter", "days": 1, "festival": True},
        {"name": "Alturiak", "days": 30},
        {"name": "Ches", "days": 30},
        {"name": "Tarsakh", "days": 30},
        {"name": "Greengrass", "days": 1, "festival": True},
        {"name": "Mirtul", "days": 30},
        {"name": "Kythorn", "days": 30},
        {"name": "Flamerule", "days": 30},
        {"name": "Midsummer", "days": 1, "festival": True},
        {"name": "Eleasis", "days": 30},
        {"name": "Eleint", "days": 30},
        {"name": "Highharvestide", "days": 1, "festival": True},
        {"name": "Marpenoth", "days": 30},
        {"name": "Uktar", "days": 30},
        {"name": "Feast of the Moon", "days": 1, "festival": True},
        {"name": "Nightal", "days": 30},
    ],
    "leap": {"every_years": 4, "month_index": 9, "extra_days": 1},  # Midsummer +1 (Shieldmeet)
    "seasons": [
        {"name": "Winter", "start_month_index": 0},
        {"name": "Spring", "start_month_index": 3},
        {"name": "Summer", "start_month_index": 6},
        {"name": "Autumn", "start_month_index": 12},
    ],
}

PRESETS: dict[str, dict[str, Any]] = {"generic": GENERIC, "harptos": HARPTOS}
DEFAULT_CALENDAR: dict[str, Any] = GENERIC
