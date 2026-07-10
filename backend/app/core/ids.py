"""UUIDv7 generation — time-ordered ids (index-friendly, merge-safe for future sharing).

Python's stdlib gained ``uuid.uuid7`` only in 3.14; we ship a small RFC-9562
implementation so the codebase runs on 3.12+ (our declared floor).
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a UUIDv7: 48-bit big-endian Unix-ms timestamp + 74 random bits."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits; we use 74

    value = (unix_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= ((rand >> 14) & 0x0FFF) << 64  # 12 bits rand_a
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand & 0x3FFF_FFFF_FFFF_FFFF  # 62 bits rand_b
    return uuid.UUID(int=value)


def new_id() -> str:
    """String form used for all primary keys."""
    return str(uuid7())
