"""CalendarMath: pure conversion between campaign *seconds* and human date parts.

The campaign clock is stored as integer seconds since the calendar epoch (docs/07, §9.2) —
fine enough for 6-second combat rounds and real-time ticking. All arithmetic is integer
until formatting. ``frontend/src/lib/calendar.ts`` is a parity port checked against shared
golden fixtures (tests/fixtures/calendar_golden.json).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class DateParts(TypedDict):
    total_days: int
    year: int
    month_index: int
    day_of_month: int  # 0-based
    day_of_year: int  # 0-based
    weekday_index: int
    hour: int
    minute: int
    second: int
    is_festival: bool
    season: str | None


class FormattedDate(TypedDict):
    label: str  # e.g. "Hammer 12, 1372 DR"
    weekday: str
    month: str
    day: int  # 1-based
    year: int
    time: str  # "HH:MM:SS"
    season: str | None
    seconds: int


@dataclass(frozen=True)
class CalendarMath:
    cal: dict[str, Any]

    # -- basic dimensions ---------------------------------------------------
    @property
    def seconds_per_minute(self) -> int:
        return int(self.cal.get("seconds_per_minute", 60))

    @property
    def minutes_per_hour(self) -> int:
        return int(self.cal["minutes_per_hour"])

    @property
    def hours_per_day(self) -> int:
        return int(self.cal["hours_per_day"])

    @property
    def seconds_per_hour(self) -> int:
        return self.minutes_per_hour * self.seconds_per_minute

    @property
    def seconds_per_day(self) -> int:
        return self.hours_per_day * self.seconds_per_hour

    @property
    def start_year(self) -> int:
        return int(self.cal.get("start_year", 1))

    @property
    def _weekdays(self) -> list[str]:
        return list(self.cal["weekdays"])

    @property
    def _months(self) -> list[dict[str, Any]]:
        return list(self.cal["months"])

    # -- leap handling ------------------------------------------------------
    def _is_leap(self, year: int) -> bool:
        leap = self.cal.get("leap")
        if not leap or not leap.get("every_years"):
            return False
        return year % int(leap["every_years"]) == 0

    def _month_days(self, month_index: int, year: int) -> int:
        base = int(self._months[month_index]["days"])
        leap = self.cal.get("leap")
        if leap and self._is_leap(year) and int(leap["month_index"]) == month_index:
            base += int(leap["extra_days"])
        return base

    def _days_in_year(self, year: int) -> int:
        return sum(self._month_days(i, year) for i in range(len(self._months)))

    # -- conversions --------------------------------------------------------
    def to_parts(self, seconds: int) -> DateParts:
        spd = self.seconds_per_day
        day_index = seconds // spd  # floors toward -inf (correct for negatives)
        tod = seconds - day_index * spd
        hour, rem = divmod(tod, self.seconds_per_hour)
        minute, second = divmod(rem, self.seconds_per_minute)

        # Locate the year.
        year = self.start_year
        remaining = day_index
        if remaining >= 0:
            while remaining >= self._days_in_year(year):
                remaining -= self._days_in_year(year)
                year += 1
        else:
            while remaining < 0:
                year -= 1
                remaining += self._days_in_year(year)
        day_of_year = remaining

        # Locate the month/day within the year.
        month_index = 0
        while remaining >= self._month_days(month_index, year):
            remaining -= self._month_days(month_index, year)
            month_index += 1
        day_of_month = remaining

        weekday_index = day_index % len(self._weekdays)
        return DateParts(
            total_days=day_index,
            year=year,
            month_index=month_index,
            day_of_month=day_of_month,
            day_of_year=day_of_year,
            weekday_index=weekday_index,
            hour=hour,
            minute=minute,
            second=second,
            is_festival=bool(self._months[month_index].get("festival", False)),
            season=self._season_for(month_index),
        )

    def _season_for(self, month_index: int) -> str | None:
        seasons = self.cal.get("seasons")
        if not seasons:
            return None
        # The active season is the one with the greatest start_month_index <= month_index,
        # wrapping so months before the first season belong to the last one.
        best: str | None = None
        best_start = -1
        wrap: str | None = None
        wrap_start = -1
        for s in seasons:
            start = int(s["start_month_index"])
            if start <= month_index and start > best_start:
                best, best_start = s["name"], start
            if start > wrap_start:
                wrap, wrap_start = s["name"], start
        return best if best is not None else wrap

    def format(self, seconds: int) -> FormattedDate:
        p = self.to_parts(seconds)
        month = self._months[p["month_index"]]["name"]
        day = p["day_of_month"] + 1
        time = f"{p['hour']:02d}:{p['minute']:02d}:{p['second']:02d}"
        epoch = self.cal.get("epoch_label", "")
        label = f"{month} {day}, {p['year']} {epoch}".strip()
        return FormattedDate(
            label=label,
            weekday=self._weekdays[p["weekday_index"]],
            month=month,
            day=day,
            year=p["year"],
            time=time,
            season=p["season"],
            seconds=seconds,
        )

    # -- helpers for the UI / advancement ----------------------------------
    def to_seconds(self, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> int:
        return (
            days * self.seconds_per_day
            + hours * self.seconds_per_hour
            + minutes * self.seconds_per_minute
            + seconds
        )
