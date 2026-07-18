"""Dice engine — the one place a die is actually rolled.

Lives in ``core`` because both ``rules`` (attack actions) and ``playbook`` (combat,
initiative) need it, and the import-linter layer contract forbids either importing the
other. Nothing here knows about any game system: an expression in, a result out.

Every roll goes through an injectable ``rng``, so a seeded ``random.Random`` makes any
caller deterministic under test without stubbing the module.

This matters more than it looks: combat never rolls inside the reducer (ADR-005). A roll
resolves *here*, and only its literal result is written to the action log — which is what
keeps folding that log deterministic and undo/redo exact.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal, NamedTuple

Mode = Literal["normal", "advantage", "disadvantage"]

#: Sanity bounds. A real stat block never exceeds these; an expression that does is a typo
#: or an attack, and either way we would rather raise than allocate a million ints.
MAX_COUNT = 100
MAX_SIDES = 1000

_DIE_RE = re.compile(r"^(\d*)d(\d+)$", re.IGNORECASE)
_RNG = random.Random()


class BadExpression(ValueError):
    """The expression is not parseable dice notation."""


class _Term(NamedTuple):
    # ``qty``, not ``count`` — a NamedTuple field named ``count`` shadows ``tuple.count``.
    qty: int
    sides: int
    sign: int  # +1 or -1


@dataclass(frozen=True)
class DieRoll:
    sides: int
    value: int
    #: False for the die discarded by advantage/disadvantage — kept in the result so the
    #: UI can show "17 (17, 9)" rather than silently dropping half the story.
    kept: bool
    sign: int


@dataclass(frozen=True)
class RollResult:
    expression: str
    mode: Mode
    dice: list[DieRoll]
    modifier: int
    total: int
    #: Natural 20/1 on a lone d20 (the kept one, under advantage). Both False otherwise.
    critical: bool
    fumble: bool


def _tokenize(expr: str) -> list[tuple[int, str]]:
    """Split ``"2d6+3-1d4"`` into ``[(1, "2d6"), (1, "3"), (-1, "1d4")]``."""
    s = expr.replace(" ", "")
    if not s:
        raise BadExpression(expr)

    out: list[tuple[int, str]] = []
    sign = 1
    start = 0
    if s[0] in "+-":
        sign = -1 if s[0] == "-" else 1
        start = 1

    buf = ""
    for ch in s[start:]:
        if ch in "+-":
            if not buf:
                raise BadExpression(expr)
            out.append((sign, buf))
            buf = ""
            sign = -1 if ch == "-" else 1
        else:
            buf += ch
    if not buf:
        raise BadExpression(expr)
    out.append((sign, buf))
    return out


def parse(expr: str) -> tuple[list[_Term], int]:
    """Parse dice notation into its die terms and a flat modifier.

    Accepts ``NdM`` terms and bare integers joined by ``+``/``-``: ``1d20+5``, ``2d6-1``,
    ``1d8``, ``2d8+1d6+3``, ``1d20-1d4`` (bane), ``7``. Bare ``dM`` means ``1dM``.
    """
    terms: list[_Term] = []
    modifier = 0
    for sign, token in _tokenize(expr):
        m = _DIE_RE.match(token)
        if m:
            qty = int(m.group(1)) if m.group(1) else 1
            sides = int(m.group(2))
            if not (1 <= qty <= MAX_COUNT) or not (1 <= sides <= MAX_SIDES):
                raise BadExpression(expr)
            terms.append(_Term(qty, sides, sign))
        elif token.isdigit():
            modifier += sign * int(token)
        else:
            raise BadExpression(expr)
    if not terms and not modifier:
        raise BadExpression(expr)
    return terms, modifier


def bounds(expr: str) -> tuple[int, int]:
    """The lowest and highest totals ``expr`` can produce.

    Random tables use this to check that their rows cover every possible roll exactly once.
    """
    terms, modifier = parse(expr)
    low = high = modifier
    for term in terms:
        if term.sign > 0:
            low += term.qty
            high += term.qty * term.sides
        else:
            low -= term.qty * term.sides
            high -= term.qty
    return low, high


def _advantage_target(terms: list[_Term]) -> _Term | None:
    """The lone additive d20 that advantage applies to, if the expression has exactly one.

    Advantage on ``2d6`` is meaningless, and on ``1d20+1d20`` it is ambiguous — in both
    cases the mode is ignored rather than guessed at.
    """
    d20s = [t for t in terms if t.sides == 20 and t.qty == 1 and t.sign == 1]
    return d20s[0] if len(d20s) == 1 else None


def roll(expr: str, *, mode: Mode = "normal", rng: random.Random | None = None) -> RollResult:
    """Roll ``expr``, returning every die face along with the total.

    ``mode`` rolls a second d20 and keeps the higher/lower — but only when the expression
    contains exactly one additive d20 (see ``_advantage_target``); otherwise it is ignored.
    """
    terms, modifier = parse(expr)
    r = rng if rng is not None else _RNG
    adv_target = _advantage_target(terms) if mode != "normal" else None

    dice: list[DieRoll] = []
    total = modifier
    for term in terms:
        if term is adv_target:
            pair = [r.randint(1, term.sides) for _ in range(2)]
            keep = max(pair) if mode == "advantage" else min(pair)
            # Only the first matching face is the kept one — on a tie the other is the discard.
            taken = False
            for value in pair:
                is_kept = not taken and value == keep
                taken = taken or is_kept
                dice.append(DieRoll(term.sides, value, is_kept, term.sign))
            total += term.sign * keep
        else:
            for _ in range(term.qty):
                value = r.randint(1, term.sides)
                dice.append(DieRoll(term.sides, value, True, term.sign))
                total += term.sign * value

    kept_d20 = [d for d in dice if d.kept and d.sides == 20 and d.sign == 1]
    lone_d20 = kept_d20[0] if len(kept_d20) == 1 else None
    return RollResult(
        expression=expr,
        mode=mode,
        dice=dice,
        modifier=modifier,
        total=total,
        critical=lone_d20 is not None and lone_d20.value == 20,
        fumble=lone_d20 is not None and lone_d20.value == 1,
    )


def max_dice(expr: str) -> str:
    """Double every die count in ``expr`` — 5e's ``double_dice`` crit rule, applied as data.

    The *rule* belongs to the rule system, which asks for it by name; the arithmetic is
    generic, so it lives here rather than leaking dice parsing into a plugin.
    """
    terms, modifier = parse(expr)
    parts: list[str] = []
    for i, term in enumerate(terms):
        sign = "-" if term.sign < 0 else ("+" if i else "")
        parts.append(f"{sign}{term.qty * 2}d{term.sides}")
    if modifier:
        parts.append(f"{'+' if modifier > 0 else '-'}{abs(modifier)}")
    return "".join(parts)
