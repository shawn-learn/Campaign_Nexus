"""Pure combat-state reducer (ADR-005): state = fold(actions).

Combat is event-sourced *inside* an encounter run: the state is never stored per-field,
only derived by folding the action log. Undo/redo is a cursor into that log. This module
is a system-agnostic reducer (HP, conditions, turn order as data); it has a byte-for-byte
TypeScript twin (frontend/src/lib/combatReducer.ts) verified against shared golden fixtures.
"""

from __future__ import annotations

from typing import Any

Action = dict[str, Any]
State = dict[str, Any]


def initial_state() -> State:
    return {"round": 1, "turn_index": 0, "order": [], "combatants": {}}


def _reorder(state: State) -> None:
    combatants = state["combatants"]
    ids = sorted(combatants, key=lambda i: (-combatants[i]["initiative"], i))
    state["order"] = ids
    state["turn_index"] = min(state["turn_index"], len(ids) - 1) if ids else 0


def apply_action(state: State, action: Action) -> State:
    kind = action["type"]
    combatants: dict[str, Any] = state["combatants"]

    if kind == "add_combatant":
        cid = action["id"]
        max_hp = int(action["max_hp"])
        hp = int(action.get("hp", max_hp))
        combatants[cid] = {
            "id": cid, "name": action["name"], "side": action.get("side", "foe"),
            "max_hp": max_hp, "hp": hp, "temp_hp": 0,
            "initiative": int(action.get("initiative", 0)),
            "conditions": [], "concentrating": False, "defeated": hp <= 0,
        }
        _reorder(state)
    elif kind == "set_initiative":
        m = combatants.get(action["id"])
        if m:
            m["initiative"] = int(action["value"])
            _reorder(state)
    elif kind == "damage":
        m = combatants.get(action["id"])
        if m:
            amount = int(action["amount"])
            absorbed = min(m["temp_hp"], amount)
            m["temp_hp"] -= absorbed
            amount -= absorbed
            m["hp"] = max(0, m["hp"] - amount)
            m["defeated"] = m["hp"] == 0
            if m["hp"] == 0:
                m["concentrating"] = False
    elif kind == "heal":
        m = combatants.get(action["id"])
        if m:
            m["hp"] = min(m["max_hp"], m["hp"] + int(action["amount"]))
            if m["hp"] > 0:
                m["defeated"] = False
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
    elif kind == "next_turn":
        if state["order"]:
            state["turn_index"] += 1
            if state["turn_index"] >= len(state["order"]):
                state["turn_index"] = 0
                state["round"] += 1
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
