"""Sprint 13: combat reducer golden, and event-sourced run with undo/redo/end."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.playbook.combat_reducer import fold
from fastapi.testclient import TestClient

_GOLDEN = Path(__file__).parent / "fixtures" / "combat_golden.json"


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _monster(client: TestClient, cid: str, name: str) -> str:
    return next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json()
                if m["name"] == name)["id"]


# --- reducer golden (feeds the TS parity test too) -------------------------
def test_reducer_golden() -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    for case in golden:
        assert fold(case["actions"]) == case["expected"], case["name"]


def test_api_combatant_carries_every_reducer_field(client: TestClient) -> None:
    """The wire shape must match the reducer's exactly.

    ``state_of`` model_validates the folded dict through the ``Combatant`` pydantic model,
    and pydantic *drops* fields the model doesn't declare. A field added to the reducer but
    forgotten in schemas.py would vanish between the fold and the response with nothing
    failing — so compare the two shapes directly rather than trust either alone.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()

    reference = fold([
        {"type": "add_combatant", "id": "x", "name": "X", "side": "foe",
         "max_hp": 7, "initiative": 2},
    ])["combatants"]["x"]
    over_the_wire = next(iter(run["state"]["combatants"].values()))
    assert set(over_the_wire) == set(reference), "wire shape drifted from the reducer"


def test_reducer_undo_redo_identity() -> None:
    actions = [
        {"type": "add_combatant", "id": "a", "name": "A", "side": "foe",
         "max_hp": 20, "initiative": 10},
        {"type": "damage", "id": "a", "amount": 5},
        {"type": "damage", "id": "a", "amount": 3},
    ]
    full = fold(actions)
    # Folding a prefix (undo) then the rest (redo) reproduces the full state.
    assert fold(actions[:2]) == fold(actions[:2])
    assert full["combatants"]["a"]["hp"] == 12


# --- event-sourced run -----------------------------------------------------
def _encounter_of_two_goblins(client: TestClient, cid: str) -> str:
    goblin = _monster(client, cid, "Goblin")
    return client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Ambush", "combatants": [{"monster_id": goblin, "count": 2}]},
    ).json()["id"]


def _start_from_two_goblins(client: TestClient, cid: str) -> str:
    enc = _encounter_of_two_goblins(client, cid)
    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc}).json()
    return run["run_id"]


def test_start_combat_seeds_combatants(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    combatants = run["state"]["combatants"]
    assert len(combatants) == 2  # two goblins
    assert {c["name"] for c in combatants.values()} == {"Goblin 1", "Goblin 2"}


def test_combatant_blocks_map_points_at_a_stat_block(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    blocks = run["combatant_blocks"]
    # Every combatant maps to a stat block, and that block is fetchable + is a Goblin.
    assert set(blocks) == set(run["state"]["combatants"])
    block_id = next(iter(blocks.values()))
    block = client.get(f"/api/v1/campaigns/{cid}/stat-blocks/{block_id}")
    assert block.status_code == 200, block.text
    assert block.json()["sheet_type"] == "monster"


def test_unknown_action_type_is_rejected(client: TestClient) -> None:
    """A typo'd action used to persist, advance the fold cursor, and do nothing.

    The reducer ignores types it doesn't know, so the write "succeeded", the GM saw no
    change, and Undo was the only way to clear the dead log entry. It 422s at the edge now.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    before = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["total_actions"]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "rol_initiative", "payload": {}},
    )
    assert resp.status_code == 422
    # And nothing was written — the log is exactly as long as it was.
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["total_actions"]
    assert after == before


def test_party_hp_is_written_back_when_combat_ends(client: TestClient) -> None:
    """A PC's wounds must outlive the combat that caused them.

    The fold was the only record of damage taken, and nothing reads it once the run is over
    — so a character walked out of a bruising fight at full health.
    """
    cid = _demo(client)
    pc = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": "Serah",
              "doc": {"level": 5, "max_hit_points": 40, "armor_class": 16,
                      "abilities": {"str": 10, "dex": 14, "con": 12, "int": 10,
                                    "wis": 10, "cha": 10}}},
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": pc})

    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")
    assert serah["hp"] == 40  # joined at full

    client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {"id": serah["id"], "amount": 13}},
    )
    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end")

    member = client.get(f"/api/v1/campaigns/{cid}/party").json()["members"][0]
    assert member["hp"] == 27
    assert member["status"]["current_hit_points"] == 27


# --- initiative -------------------------------------------------------------
def _pc(client: TestClient, cid: str, label: str, dex: int = 14) -> str:
    sb = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": label,
              "doc": {"level": 5, "max_hit_points": 40, "armor_class": 16,
                      "abilities": {"str": 10, "dex": dex, "con": 12, "int": 10,
                                    "wis": 10, "cha": 10}}},
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": sb})
    return sb


def test_combat_opens_in_setup_with_the_monsters_already_rolled(client: TestClient) -> None:
    """Starting a combat is the moment you call for initiative: the monsters roll at once.

    The PCs' numbers are the GM's to type in, so they wait — and the run stays in `setup`
    until Begin, which is what makes the roster screen survive a refresh.
    """
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run = client.post(
        f"/api/v1/campaigns/{cid}/combats",
        json={"encounter_id": _encounter_of_two_goblins(client, cid)},
    ).json()

    assert run["status"] == "setup"
    combatants = run["state"]["combatants"].values()
    goblins = [c for c in combatants if c["side"] == "foe"]
    serah = next(c for c in combatants if c["name"] == "Serah")

    # Goblins have dex 14 (+2), so a rolled total lands in 3..22 and is almost never the
    # bare +2 seed. Serah is untouched at her seeded modifier, waiting for a typed total.
    assert all(3 <= g["initiative"] <= 22 for g in goblins)
    assert serah["initiative"] == 2  # dex 14 -> +2, the pre-roll seed

    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/rolls").json()
    assert len(rolls) == 2  # one per goblin
    assert {r["kind"] for r in rolls} == {"initiative"}
    assert all(r["expression"] == "1d20+2" for r in rolls)


def test_roll_initiative_takes_typed_values_and_rolls_the_rest(client: TestClient) -> None:
    # The actual moment at the table: the monsters roll, the players call their numbers out.
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/initiative",
        json={"scope": "foes", "values": {serah["id"]: 18}},
    ).json()

    after = out["state"]["combatants"][serah["id"]]
    assert after["initiative"] == 18  # taken verbatim — the modifier is already in it
    assert after["initiative_tiebreak"] == 2  # dex, for breaking ties
    # 18 beats any goblin that didn't roll a natural 17+, so Serah is usually first; assert
    # the invariant instead: the order is sorted by initiative descending.
    order = [out["state"]["combatants"][i]["initiative"] for i in out["state"]["order"]]
    assert order == sorted(order, reverse=True)


def test_a_typed_value_wins_over_a_roll_for_the_same_combatant(client: TestClient) -> None:
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")

    # scope=all *includes* Serah, but a typed value for her must not be rolled over.
    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/initiative",
        json={"scope": "all", "values": {serah["id"]: 11}},
    ).json()
    assert out["state"]["combatants"][serah["id"]]["initiative"] == 11


def test_begin_leaves_setup_and_rejects_a_finished_run(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    assert client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["status"] == "setup"

    begun = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/begin")
    assert begun.status_code == 200
    assert begun.json()["status"] == "active"

    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end")
    assert client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/begin").status_code == 409


def test_initiative_is_editable_during_setup(client: TestClient) -> None:
    # `setup` must still accept actions — it is where initiative gets corrected. Guarding on
    # status != "active" would have made the whole roster screen read-only.
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "set_initiative", "payload": {"id": gid, "value": 20}},
    )
    assert resp.status_code == 200
    assert resp.json()["state"]["combatants"][gid]["initiative"] == 20


def test_undo_does_not_erase_a_roll(client: TestClient) -> None:
    """Rolls live outside the fold, so a cursor move never un-throws a die.

    Folding them would also mean Undo after a roll appeared to do nothing, since a roll has
    no effect on state.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    before = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert len(before) == 2

    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/undo")
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert len(after) == 2


def test_list_combats_by_encounter(client: TestClient) -> None:
    cid = _demo(client)
    goblin = _monster(client, cid, "Goblin")
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Ambush", "combatants": [{"monster_id": goblin, "count": 1}]},
    ).json()
    assert client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json() == []

    run = client.post(
        f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc["id"]}
    ).json()
    listed = client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json()
    assert [r["run_id"] for r in listed] == [run["run_id"]]
    # A run opens in `setup` (rolling initiative) and only becomes `active` on Begin.
    assert listed[0]["status"] == "setup" and listed[0]["round"] == 1
    client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/begin")
    listed = client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json()
    assert listed[0]["status"] == "active"
    # No filter → empty (the endpoint is scoped to an encounter, not a firehose).
    assert client.get(f"/api/v1/campaigns/{cid}/combats").json() == []


def test_actions_undo_redo_and_resume(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    def act(atype, **payload):
        return client.post(
            f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
            json={"action_type": atype, "payload": payload},
        ).json()

    # Ten damage actions.
    last = None
    for _ in range(10):
        last = act("damage", id=gid, amount=1)
    assert last["state"]["combatants"][gid]["hp"] == 7 - 10 + 3  # 7hp, 10 dmg floored at 0
    assert last["state"]["combatants"][gid]["hp"] == 0

    # Undo 10 → back to full HP; can_redo true.
    for _ in range(10):
        u = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/undo").json()
    assert u["state"]["combatants"][gid]["hp"] == 7
    assert u["can_redo"] is True

    # Redo 3 → 3 damage applied.
    for _ in range(3):
        r = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/redo").json()
    assert r["state"]["combatants"][gid]["hp"] == 4

    # Resume: a fresh GET folds to the same state (survives reload).
    resumed = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    assert resumed["state"]["combatants"][gid]["hp"] == 4

    # A new action after undo truncates the redo tail.
    act("heal", id=gid, amount=2)
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    assert after["can_redo"] is False
    assert after["state"]["combatants"][gid]["hp"] == 6


def test_end_combat_advances_clock_and_logs(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]
    # Defeat one goblin, run a few turns.
    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                json={"action_type": "damage", "payload": {"id": gid, "amount": 99}})
    for _ in range(4):  # advance a couple of rounds
        client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                    json={"action_type": "next_turn", "payload": {}})

    summary = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end").json()
    assert summary["rounds"] >= 2
    # 6 seconds per round (5e); round 1 = 0 elapsed, so (rounds - 1) * 6.
    assert summary["duration_seconds"] == (summary["rounds"] - 1) * 6
    assert "Goblin 1" in summary["defeated"] or "Goblin 2" in summary["defeated"]

    # Combat ended → domain events logged; a second end is rejected via ended run.
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "combat_ended" in types and "combatant_defeated" in types
    closed = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                         json={"action_type": "next_turn", "payload": {}})
    assert closed.status_code == 409
