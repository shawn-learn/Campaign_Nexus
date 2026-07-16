"""Coin math. Copper pieces (cp) are the smallest unit and the storage unit.

5e coin values: 1 pp = 10 gp; 1 gp = 2 ep = 10 sp = 100 cp.
"""

from __future__ import annotations

import re

_COIN_CP = {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}
_PRICE_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*(pp|gp|ep|sp|cp)\s*$", re.IGNORECASE)


def parse_cp(text: str | None) -> int | None:
    """Parse a coin string like ``"2 sp"`` / ``"250 gp"`` into copper. None if unparseable."""
    if not text:
        return None
    m = _PRICE_RE.match(text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", "")) * _COIN_CP[m.group(2).lower()])


def format_cp(cp: int) -> str:
    """A single shop-friendly coin (gp preferred, then ep/sp/cp); platinum is skipped."""
    if cp <= 0:
        return "0 gp"
    if cp % 100 == 0:
        return f"{cp // 100} gp"
    if cp % 50 == 0:
        return f"{cp // 50} ep"
    if cp % 10 == 0:
        return f"{cp // 10} sp"
    return f"{cp} cp"


def coin_split(cp: int) -> tuple[int, int, int]:
    """Split copper into (gp, sp, cp) — the three denominations a wallet tracks."""
    cp = max(0, cp)
    gp, rem = divmod(cp, 100)
    sp, c = divmod(rem, 10)
    return gp, sp, c


def format_coins(cp: int) -> str:
    """Full wallet breakdown, e.g. 1235 -> ``"12 gp 3 sp 5 cp"``. Zero -> ``"0 gp"``."""
    gp, sp, c = coin_split(cp)
    parts = []
    if gp:
        parts.append(f"{gp} gp")
    if sp:
        parts.append(f"{sp} sp")
    if c:
        parts.append(f"{c} cp")
    return " ".join(parts) if parts else "0 gp"


def cp_to_gp_ceil(cp: int) -> int:
    return (cp + 99) // 100


def cp_to_gp_floor(cp: int) -> int:
    return cp // 100
