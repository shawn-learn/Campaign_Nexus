"""Dice engine (app/core/dice.py).

Most cases drive a scripted RNG so the assertions are exact rather than seed-dependent;
the seeded-``Random`` cases cover the property that actually matters to combat — the same
seed replays the same roll, which is what lets a rolled result be trusted in the log.
"""

from __future__ import annotations

import random

import pytest
from app.core import dice


class ScriptedRandom(random.Random):
    """Hands back pre-set faces in order, so a test can state the exact dice it means."""

    def __init__(self, values: list[int]) -> None:
        super().__init__()
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:  # type: ignore[override]
        return self._values.pop(0)


# --- parsing --------------------------------------------------------------- #


@pytest.mark.parametrize(
    "expr,terms,modifier",
    [
        ("1d20+5", [(1, 20, 1)], 5),
        ("2d6-1", [(2, 6, 1)], -1),
        ("1d8", [(1, 8, 1)], 0),
        ("d8", [(1, 8, 1)], 0),
        ("2d8+1d6+3", [(2, 8, 1), (1, 6, 1)], 3),
        ("1d20-1d4", [(1, 20, 1), (1, 4, -1)], 0),
        ("7", [], 7),
        (" 1d20 + 5 ", [(1, 20, 1)], 5),
        ("-1d4+2", [(1, 4, -1)], 2),
    ],
)
def test_parse(expr: str, terms: list[tuple[int, int, int]], modifier: int) -> None:
    parsed, mod = dice.parse(expr)
    assert [tuple(t) for t in parsed] == terms
    assert mod == modifier


@pytest.mark.parametrize(
    "expr", ["", "   ", "d", "1d", "d0", "0d6", "1d20+", "+", "2x6", "1d20++5", "abc", "1d0"]
)
def test_parse_rejects_garbage(expr: str) -> None:
    with pytest.raises(dice.BadExpression):
        dice.parse(expr)


def test_parse_rejects_absurd_sizes() -> None:
    # Guard rails, not opinions: nothing real rolls 200 dice or a d5000.
    with pytest.raises(dice.BadExpression):
        dice.parse(f"{dice.MAX_COUNT + 1}d6")
    with pytest.raises(dice.BadExpression):
        dice.parse(f"1d{dice.MAX_SIDES + 1}")


# --- rolling --------------------------------------------------------------- #


def test_roll_sums_dice_and_modifier() -> None:
    result = dice.roll("2d6+3", rng=ScriptedRandom([4, 5]))
    assert result.total == 12
    assert [d.value for d in result.dice] == [4, 5]
    assert result.modifier == 3
    assert all(d.kept for d in result.dice)


def test_roll_subtracts_negative_dice_terms() -> None:
    # Bane: 1d20-1d4. The d4 is subtracted, not added.
    result = dice.roll("1d20-1d4", rng=ScriptedRandom([15, 3]))
    assert result.total == 12


def test_roll_flat_modifier_only() -> None:
    result = dice.roll("7", rng=ScriptedRandom([]))
    assert result.total == 7
    assert result.dice == []


# --- advantage / disadvantage ---------------------------------------------- #


def test_advantage_keeps_the_higher_die() -> None:
    result = dice.roll("1d20+5", mode="advantage", rng=ScriptedRandom([9, 17]))
    assert result.total == 22
    assert len(result.dice) == 2
    assert [d.value for d in result.dice if d.kept] == [17]
    assert [d.value for d in result.dice if not d.kept] == [9]


def test_disadvantage_keeps_the_lower_die() -> None:
    result = dice.roll("1d20+5", mode="disadvantage", rng=ScriptedRandom([9, 17]))
    assert result.total == 14
    assert [d.value for d in result.dice if d.kept] == [9]


def test_advantage_on_a_tie_keeps_exactly_one() -> None:
    result = dice.roll("1d20", mode="advantage", rng=ScriptedRandom([12, 12]))
    assert result.total == 12
    assert len([d for d in result.dice if d.kept]) == 1


def test_advantage_ignored_when_no_lone_d20() -> None:
    # Advantage on 2d6 is meaningless — roll it straight rather than guess.
    result = dice.roll("2d6", mode="advantage", rng=ScriptedRandom([3, 4]))
    assert result.total == 7
    assert len(result.dice) == 2


def test_advantage_ignored_when_two_d20s_are_ambiguous() -> None:
    result = dice.roll("1d20+1d20", mode="advantage", rng=ScriptedRandom([5, 6]))
    assert result.total == 11
    assert len(result.dice) == 2


# --- crit / fumble --------------------------------------------------------- #


def test_natural_twenty_is_critical() -> None:
    result = dice.roll("1d20+5", rng=ScriptedRandom([20]))
    assert result.critical
    assert not result.fumble


def test_natural_one_is_a_fumble() -> None:
    result = dice.roll("1d20+5", rng=ScriptedRandom([1]))
    assert result.fumble
    assert not result.critical


def test_crit_follows_the_kept_die_under_advantage() -> None:
    # The discarded 20 must not count; the kept 3 is what happened.
    result = dice.roll("1d20", mode="disadvantage", rng=ScriptedRandom([20, 3]))
    assert result.total == 3
    assert not result.critical


def test_crit_only_applies_to_a_lone_d20() -> None:
    result = dice.roll("2d20", rng=ScriptedRandom([20, 20]))
    assert not result.critical


def test_damage_dice_never_crit() -> None:
    result = dice.roll("2d6+3", rng=ScriptedRandom([6, 6]))
    assert not result.critical
    assert not result.fumble


# --- determinism ----------------------------------------------------------- #


def test_same_seed_replays_the_same_roll() -> None:
    a = dice.roll("1d20+5", rng=random.Random(42))
    b = dice.roll("1d20+5", rng=random.Random(42))
    assert a.total == b.total
    assert [d.value for d in a.dice] == [d.value for d in b.dice]


def test_rolls_stay_in_range() -> None:
    rng = random.Random(7)
    for _ in range(200):
        result = dice.roll("1d20+5", rng=rng)
        assert 6 <= result.total <= 25
        assert all(1 <= d.value <= 20 for d in result.dice)


def test_roll_without_rng_still_works() -> None:
    result = dice.roll("1d20")
    assert 1 <= result.total <= 20


# --- crit damage ----------------------------------------------------------- #


@pytest.mark.parametrize(
    "expr,doubled",
    [
        ("2d8+4", "4d8+4"),
        ("1d6", "2d6"),
        ("1d8+1d6+2", "2d8+2d6+2"),
        ("2d6-1", "4d6-1"),
    ],
)
def test_max_dice_doubles_dice_but_not_the_modifier(expr: str, doubled: str) -> None:
    assert dice.max_dice(expr) == doubled


def test_max_dice_output_is_reparseable() -> None:
    # The doubled expression feeds straight back into roll(), so it must round-trip.
    result = dice.roll(dice.max_dice("2d8+4"), rng=ScriptedRandom([1, 2, 3, 4]))
    assert result.total == 14
