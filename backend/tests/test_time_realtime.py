"""Combat drives the clock at 6s/round; real time ticks and is paused during combat."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _one_goblin_combat(client: TestClient, cid: str) -> str:
    goblin = next(
        m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json() if m["name"] == "Goblin"
    )["id"]
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Skirmish", "combatants": [{"monster_id": goblin, "count": 1}]},
    ).json()
    return client.post(f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc["id"]}).json()[
        "run_id"
    ]


def _clock(client: TestClient, cid: str) -> int:
    return client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]


def test_combat_ticks_six_seconds_per_round(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _one_goblin_combat(client, cid)
    base = _clock(client, cid)

    def next_turn() -> None:
        client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                    json={"action_type": "next_turn", "payload": {}})

    # Order length 1 → each next_turn advances a round → +6 seconds.
    next_turn()
    assert _clock(client, cid) == base + 6
    next_turn()
    assert _clock(client, cid) == base + 12

    # Undo rewinds the round and the clock with it.
    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/undo")
    assert _clock(client, cid) == base + 6

    # Real time is paused while a combat is running.
    assert client.get(f"/api/v1/campaigns/{cid}/clock").json()["realtime_paused"] is True

    summary = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end").json()
    assert summary["duration_seconds"] == (summary["rounds"] - 1) * 6
    assert client.get(f"/api/v1/campaigns/{cid}/clock").json()["realtime_paused"] is False


def test_realtime_ticks_and_pauses_for_combat(client: TestClient) -> None:
    cid = _demo(client)
    enabled = client.post(f"/api/v1/campaigns/{cid}/clock/realtime", json={"enabled": True}).json()
    assert enabled["realtime_enabled"] is True

    time.sleep(1.1)
    ticked = _clock(client, cid)
    assert ticked >= 1  # ~1 real second banked into the clock

    # Starting combat pauses real time; the clock stops creeping.
    run_id = _one_goblin_combat(client, cid)
    at_combat = _clock(client, cid)
    time.sleep(1.1)
    assert _clock(client, cid) == at_combat  # frozen (realtime paused, no rounds passed)

    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end")
    resumed_base = _clock(client, cid)
    time.sleep(1.1)
    assert _clock(client, cid) >= resumed_base + 1  # real time resumed


def test_disable_realtime_banks_elapsed(client: TestClient) -> None:
    cid = _demo(client)
    client.post(f"/api/v1/campaigns/{cid}/clock/realtime", json={"enabled": True})
    time.sleep(1.1)
    off = client.post(f"/api/v1/campaigns/{cid}/clock/realtime", json={"enabled": False}).json()
    assert off["realtime_enabled"] is False
    banked = off["time_game"]
    assert banked >= 1
    time.sleep(1.1)
    assert _clock(client, cid) == banked  # no more ticking once disabled
