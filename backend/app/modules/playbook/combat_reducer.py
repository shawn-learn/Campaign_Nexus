"""Pure combat-state reducer (ADR-005): state = fold(actions).

Combat is event-sourced *inside* an encounter run: the state is never stored per-field,
only derived by folding the action log. Undo/redo is a cursor into that log. This module
is a system-agnostic reducer (HP, conditions, turn order as data); it has a byte-for-byte
TypeScript twin (frontend/src/lib/combatReducer.ts) verified against shared golden fixtures.

**Nothing here rolls a die, and nothing here may.** Folding the log must be deterministic —
replaying it has to land on the same state every time, or undo/redo silently corrupts the
combat. Rolls resolve server-side (``app.core.dice``) and reach this module only as literal
results: ``set_initiative {value: 17}``, never ``roll_initiative {}``.

Payload keys the reducer doesn't read are legal and ignored (``stat_block_id``, ``roll_id``),
which is how provenance rides along without touching the folded state or its fixtures.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

Action = dict[str, Any]
State = dict[str, Any]

#: The complete action vocabulary — every type ``apply_action`` below actually handles.
#: It lives here, next to the implementation, so the API's validation cannot drift from what
#: the reducer understands. Add a type here and to ``apply_action`` in the same change; an
#: unhandled name would otherwise persist to the log, advance the cursor, and do nothing.
ActionType = Literal[
    "add_combatant",
    "remove_combatant",
    "set_initiative",
    "damage",
    "heal",
    "set_temp_hp",
    "add_condition",
    "remove_condition",
    "set_concentration",
    "death_save",
    "legendary_use",
    "cast_spell",
    "next_turn",
]
ACTION_TYPES: tuple[str, ...] = get_args(ActionType)


def initial_state() -> State:
    return {"round": 1, "turn_index": 0, "order": [], "combatants": {}}


def _reorder(state: State) -> None:
    combatants = state["combatants"]
    # Ties break on the tiebreak (5e: the dex modifier), then on id. Before initiative was
    # ever rolled the tiebreak was moot; with real d20s, ties are common and breaking them
    # on an opaque id would be arbitrary.
    ids = sorted(
        combatants,
        key=lambda i: (
            -combatants[i]["initiative"],
            -combatants[i]["initiative_tiebreak"],
            i,
        ),
    )
    state["order"] = ids
    state["turn_index"] = min(state["turn_index"], len(ids) - 1) if ids else 0


def _defeated(combatant: dict[str, Any]) -> bool:
    """A lair at 0 hp is not a corpse — it has no hit points to lose in the first place."""
    return bool(combatant["hp"] == 0 and combatant["kind"] != "lair")


def apply_action(state: State, action: Action) -> State:
    kind = action["type"]
    combatants: dict[str, Any] = state["combatants"]

    if kind == "add_combatant":
        cid = action["id"]
        max_hp = int(action["max_hp"])
        hp = int(action.get("hp", max_hp))
        entry_kind = action.get("kind", "creature")
        legendary_max = int(action.get("legendary_max", 0))
        combatants[cid] = {
            "id": cid, "name": action["name"], "side": action.get("side", "foe"),
            # "creature" | "lair". A lair rides in the initiative order as an ordinary
            # entry (5e: count 20) so its turn needs no special case anywhere.
            "kind": entry_kind,
            "max_hp": max_hp, "hp": hp, "temp_hp": 0,
            "initiative": int(action.get("initiative", 0)),
            "initiative_tiebreak": int(action.get("initiative_tiebreak", 0)),
            "conditions": [], "concentrating": False,
            "defeated": hp <= 0 and entry_kind != "lair",
            "death_saves": {"successes": 0, "failures": 0},
            "legendary": {"max": legendary_max, "remaining": legendary_max},
            # {pool key: {"label", "level", "max", "remaining"}} — spell slots and innate
            # per-day uses, seeded by the rule system. Empty for anything that can't cast.
            # The keys are the plugin's; nothing in here reads inside them.
            "spell_pools": dict(action.get("spell_pools") or {}),
        }
        _reorder(state)
    elif kind == "set_initiative":
        m = combatants.get(action["id"])
        if m:
            m["initiative"] = int(action["value"])
            # Rolling initiative sends the tiebreak along with the value; a manual edit
            # from the rail omits it and leaves whatever the combatant was seeded with.
            if "initiative_tiebreak" in action:
                m["initiative_tiebreak"] = int(action["initiative_tiebreak"])
            _reorder(state)
    elif kind == "damage":
        m = combatants.get(action["id"])
        if m:
            already_down = m["hp"] == 0 and m["kind"] != "lair"
            amount = int(action["amount"])
            absorbed = min(m["temp_hp"], amount)
            m["temp_hp"] -= absorbed
            amount -= absorbed
            m["hp"] = max(0, m["hp"] - amount)
            m["defeated"] = _defeated(m)
            if m["hp"] == 0:
                m["concentrating"] = False
            # Hitting someone who is already down is an automatic failed death save — the
            # single most-forgotten rule at a table, and free to get right here.
            if already_down and amount > 0:
                m["death_saves"]["failures"] += 1
    elif kind == "heal":
        m = combatants.get(action["id"])
        if m:
            m["hp"] = min(m["max_hp"], m["hp"] + int(action["amount"]))
            if m["hp"] > 0:
                m["defeated"] = False
                # Back above 0: nobody is dying any more, so the clock resets.
                m["death_saves"] = {"successes": 0, "failures": 0}
    elif kind == "death_save":
        m = combatants.get(action["id"])
        if m:
            # The *outcome* was decided server-side (a natural 20 is the plugin's rule, not
            # this module's); all that happens here is bookkeeping on a literal result.
            result = action["result"]
            saves = m["death_saves"]
            if result == "crit_success":
                m["hp"] = min(m["max_hp"], 1)
                m["defeated"] = _defeated(m)
                m["death_saves"] = {"successes": 0, "failures": 0}
            elif result == "crit_fail":
                saves["failures"] += 2
            elif result == "success":
                saves["successes"] += 1
            elif result == "failure":
                saves["failures"] += 1
    elif kind == "set_temp_hp":
        m = combatants.get(action["id"])
        if m:
            m["temp_hp"] = max(0, int(action["amount"]))
    elif kind == "add_condition":
        m = combatants.get(action["id"])
        if m and action["condition"] not in m["conditions"]:
            m["conditions"].append(action["condition"])
    elif kind == "remove_condition":
        m = combatants.get(action["id"])
        if m and action["condition"] in m["conditions"]:
            m["conditions"].remove(action["condition"])
    elif kind == "set_concentration":
        m = combatants.get(action["id"])
        if m:
            m["concentrating"] = bool(action["on"])
    elif kind == "legendary_use":
        m = combatants.get(action["id"])
        if m:
            cost = int(action.get("cost", 1))
            m["legendary"]["remaining"] = max(0, m["legendary"]["remaining"] - cost)
    elif kind == "cast_spell":
        m = combatants.get(action["id"])
        # Unlike legendary actions, a spent slot never comes back on a turn: a monster's
        # pools refill because the next fight seeds fresh ones, and a character's because
        # they rested. An unknown pool is ignored — a cantrip has none, and the tracker
        # doesn't log those at all.
        if m:
            pool = m["spell_pools"].get(action.get("pool_key"))
            if pool:
                pool["remaining"] = max(0, pool["remaining"] - int(action.get("cost", 1)))
    elif kind == "next_turn":
        if state["order"]:
            state["turn_index"] += 1
            if state["turn_index"] >= len(state["order"]):
                state["turn_index"] = 0
                state["round"] += 1
            # A creature regains its spent legendary actions at the *start of its turn*
            # (5e), which is exactly now — so the reset rides the turn rather than needing
            # anyone to remember it.
            current = combatants.get(state["order"][state["turn_index"]])
            if current and current["legendary"]["max"] > 0:
                current["legendary"]["remaining"] = current["legendary"]["max"]
    elif kind == "remove_combatant":
        cid = action["id"]
        if cid in combatants:
            del combatants[cid]
            _reorder(state)

    return state


def fold(actions: list[Action]) -> State:
    state = initial_state()
    for action in actions:
        apply_action(state, action)
    return state
