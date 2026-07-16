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
def _start_from_two_goblins(client: TestClient, cid: str) -> str:
    goblin = _monster(client, cid, "Goblin")
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Ambush", "combatants": [{"monster_id": goblin, "count": 2}]},
    ).json()
    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc["id"]}).json()
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
    assert listed[0]["status"] == "active" and listed[0]["round"] == 1
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
