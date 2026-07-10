"""Real-time helpers. Campaign (in-world) time lives in the Time Engine module."""

from __future__ import annotations

from datetime import UTC, datetime


def now_real() -> datetime:
    return datetime.now(UTC)


def now_real_iso() -> str:
    """ISO-8601 UTC string — the storage form for all ``*_real`` columns."""
    return now_real().isoformat()
