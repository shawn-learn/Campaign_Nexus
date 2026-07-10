"""Time Engine context (docs/07-time-engine.md).

Owns the campaign clock and time advancement. The clock value lives on the campaign row
(``clock_time_game``, minutes since epoch); this module is its only writer, via
``advance_time``. CalendarMath converts minutes <-> human date parts.
"""
