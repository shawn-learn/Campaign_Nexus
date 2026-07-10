"""Sprint 16 — quest graph + deadlines (FR-10) and map regions/layers (FR-3).

The sprint's exit criterion is the last test in the quest section: a quest with a deadline
expires the moment the clock passes it, and the timeline says so.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _quest(client: TestClient, cid: str, name: str, **body: object) -> dict:
    resp = client.post(f"/api/v1/campaigns/{cid}/quests", json={"name": name, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _status(client: TestClient, cid: str, qid: str, status: str) -> dict:
    return client.post(f"/api/v1/campaigns/{cid}/quests/{qid}/status", json={"status": status})


def _advance(client: TestClient, cid: str, seconds: int) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance", json={"seconds": seconds, "reason": "test"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _timeline(client: TestClient, cid: str) -> list[dict]:
    return client.get(f"/api/v1/campaigns/{cid}/timeline").json()


# --------------------------------------------------------------------------- #
# Status machine
# --------------------------------------------------------------------------- #
def test_quest_is_an_entity_and_starts_unknown(client: TestClient) -> None:
    cid = _demo(client)
    quest = _quest(client, cid, "The Sunken Bell", summary="Something tolls below.")
    assert quest["status"] == "unknown"
    assert quest["quest_type"] == "side"

    # It is a real wiki entity: searchable, linkable, in the graph.
    hits = client.get(f"/api/v1/campaigns/{cid}/search", params={"q": "Sunken"}).json()
    assert any(h["id"] == quest["entity_id"] for h in hits)


def test_quest_entity_born_in_the_wiki_gets_its_row(client: TestClient) -> None:
    """A quest can be created through the plain entity API; the quest reads heal the gap."""
    cid = _demo(client)
    entity = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "quest", "name": "Rumour"}
    ).json()

    listed = client.get(f"/api/v1/campaigns/{cid}/quests").json()
    assert [q["entity_id"] for q in listed] == [entity["id"]]
    assert listed[0]["status"] == "unknown"
    # ...and it is still on the dashboard, where 'unknown' counts as unresolved.
    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    assert [q["id"] for q in dash["active_quests"]] == [entity["id"]]

    # It transitions like any other quest.
    assert _status(client, cid, entity["id"], "active").json()["status"] == "active"


def test_status_transitions_emit_timeline_entries(client: TestClient) -> None:
    cid = _demo(client)
    qid = _quest(client, cid, "Rat Problem")["entity_id"]

    assert _status(client, cid, qid, "available").json()["status"] == "available"
    assert _status(client, cid, qid, "active").json()["status"] == "active"
    assert _status(client, cid, qid, "completed").json()["status"] == "completed"

    titles = [t["title"] for t in _timeline(client, cid)]
    assert "Quest 'Rat Problem' is now available." in titles
    assert "Quest 'Rat Problem' was accepted." in titles
    assert "Quest 'Rat Problem' was completed." in titles


def test_illegal_transition_is_rejected(client: TestClient) -> None:
    cid = _demo(client)
    qid = _quest(client, cid, "Dead End", status="active")["entity_id"]
    assert _status(client, cid, qid, "completed").status_code == 200
    # Terminal: a completed quest cannot be re-accepted.
    resp = _status(client, cid, qid, "active")
    assert resp.status_code == 409
    assert "completed" in resp.json()["detail"]


def test_objectives_checklist(client: TestClient) -> None:
    cid = _demo(client)
    qid = _quest(
        client, cid, "Three Keys",
        objectives=[{"text": "Bronze key"}, {"text": "Silver key"}],
    )["entity_id"]

    quest = client.post(
        f"/api/v1/campaigns/{cid}/quests/{qid}/objectives", json={"index": 1, "done": True}
    ).json()
    assert [o["done"] for o in quest["objectives"]] == [False, True]
    assert "'Three Keys': Silver key" in [t["title"] for t in _timeline(client, cid)]

    bad = client.post(
        f"/api/v1/campaigns/{cid}/quests/{qid}/objectives", json={"index": 9, "done": True}
    )
    assert bad.status_code == 422


# --------------------------------------------------------------------------- #
# Dependency DAG
# --------------------------------------------------------------------------- #
def test_dependencies_block_and_build_a_dag(client: TestClient) -> None:
    cid = _demo(client)
    prereq = _quest(client, cid, "Find the Map")["entity_id"]
    later = _quest(client, cid, "Sail to the Isle")["entity_id"]

    quest = client.post(
        f"/api/v1/campaigns/{cid}/quests/{later}/dependencies", json={"depends_on_id": prereq}
    ).json()
    assert quest["depends_on"] == [prereq]
    assert quest["blocked_by"] == [prereq]  # prereq is not completed yet

    graph = client.get(f"/api/v1/campaigns/{cid}/quests/graph").json()
    assert {n["id"] for n in graph["nodes"]} == {prereq, later}
    # Edges point prerequisite → dependent, so the graph reads in play order.
    assert [(e["source"], e["target"]) for e in graph["edges"]] == [(prereq, later)]

    _status(client, cid, prereq, "active")
    _status(client, cid, prereq, "completed")
    assert client.get(f"/api/v1/campaigns/{cid}/quests/{later}").json()["blocked_by"] == []

    # And it can be unlinked again.
    quest = client.delete(
        f"/api/v1/campaigns/{cid}/quests/{later}/dependencies/{prereq}"
    ).json()
    assert quest["depends_on"] == []


def test_dependency_cycle_is_rejected(client: TestClient) -> None:
    cid = _demo(client)
    a = _quest(client, cid, "Alpha")["entity_id"]
    b = _quest(client, cid, "Beta")["entity_id"]
    c = _quest(client, cid, "Gamma")["entity_id"]

    for src, dst in ((b, a), (c, b)):  # b→a, c→b
        assert client.post(
            f"/api/v1/campaigns/{cid}/quests/{src}/dependencies", json={"depends_on_id": dst}
        ).status_code == 200

    # a depends_on c would close the loop a→c→b→a.
    resp = client.post(
        f"/api/v1/campaigns/{cid}/quests/{a}/dependencies", json={"depends_on_id": c}
    )
    assert resp.status_code == 409
    assert "cycle" in resp.json()["detail"]


def test_cycle_check_walks_every_branch_not_one_parent(client: TestClient) -> None:
    """A quest may depend on several others; the guard must search the whole DAG."""
    cid = _demo(client)
    root = _quest(client, cid, "Root")["entity_id"]
    left = _quest(client, cid, "Left")["entity_id"]
    right = _quest(client, cid, "Right")["entity_id"]

    for dst in (left, right):
        client.post(
            f"/api/v1/campaigns/{cid}/quests/{root}/dependencies", json={"depends_on_id": dst}
        )
    # root→{left,right}. Adding right→root closes a cycle through the *second* branch.
    resp = client.post(
        f"/api/v1/campaigns/{cid}/quests/{right}/dependencies", json={"depends_on_id": root}
    )
    assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# Deadlines (FR-10.3) — the sprint's exit criterion
# --------------------------------------------------------------------------- #
def test_setting_a_deadline_registers_a_scheduled_event(client: TestClient) -> None:
    cid = _demo(client)
    now = client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]
    qid = _quest(client, cid, "Ransom the Duke", deadline_game=now + 3600)["entity_id"]

    events = client.get(f"/api/v1/campaigns/{cid}/scheduled-events").json()
    deadline = [e for e in events if e["title"] == "Deadline: Ransom the Duke"]
    assert len(deadline) == 1
    assert deadline[0]["action_type"] == "quest_status"
    assert deadline[0]["status"] == "pending"

    # Moving the deadline replaces the pending event rather than stacking a second one.
    client.patch(f"/api/v1/campaigns/{cid}/quests/{qid}", json={"deadline_game": now + 7200})
    events = client.get(f"/api/v1/campaigns/{cid}/scheduled-events").json()
    pending = [e for e in events if e["action_type"] == "quest_status" and e["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["fire_at_game"] == now + 7200


def test_quest_expires_when_the_clock_passes_its_deadline(client: TestClient) -> None:
    """The exit criterion: time passes → the quest expires → the timeline narrates it."""
    cid = _demo(client)
    now = client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]
    qid = _quest(client, cid, "Save the Harvest", status="active", deadline_game=now + 600)[
        "entity_id"
    ]

    preview = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance/preview", json={"seconds": 1200}
    ).json()
    assert any("would be expired" in f["narrative"] for f in preview["would_fire"])
    # A dry run must not have touched anything.
    assert client.get(f"/api/v1/campaigns/{cid}/quests/{qid}").json()["status"] == "active"

    report = _advance(client, cid, 1200)
    assert [f["narrative"] for f in report["fired"]] == ["Quest 'Save the Harvest' expired."]

    quest = client.get(f"/api/v1/campaigns/{cid}/quests/{qid}").json()
    assert quest["status"] == "expired"
    assert quest["overdue"] is False  # expired quests are resolved, not overdue

    entry = [t for t in _timeline(client, cid) if t["title"] == "Quest 'Save the Harvest' expired."]
    assert len(entry) == 1
    assert entry[0]["icon"] == "⌛"
    assert entry[0]["occurred_at_game"] == now + 600  # it fired *at* the deadline, not after

    # It falls off the dashboard's active list.
    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    assert qid not in [q["id"] for q in dash["active_quests"]]


def test_completing_before_the_deadline_disarms_it(client: TestClient) -> None:
    cid = _demo(client)
    now = client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]
    qid = _quest(client, cid, "Beat the Clock", status="active", deadline_game=now + 600)[
        "entity_id"
    ]
    _status(client, cid, qid, "completed")

    report = _advance(client, cid, 1200)
    assert report["fired"] == []  # the scheduled event was cancelled with the transition
    assert client.get(f"/api/v1/campaigns/{cid}/quests/{qid}").json()["status"] == "completed"


def test_overdue_flag_and_dashboard_brief(client: TestClient) -> None:
    cid = _demo(client)
    now = client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]
    _quest(client, cid, "Urgent Errand", status="active", deadline_game=now + 60)

    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    brief = next(q for q in dash["active_quests"] if q["name"] == "Urgent Errand")
    assert brief["status"] == "active"
    assert brief["overdue"] is False
    assert brief["deadline_label"]


# --------------------------------------------------------------------------- #
# Maps II: regions + layers
# --------------------------------------------------------------------------- #
def _png(width: int, height: int) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def _tmp_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _upload(client: TestClient, cid: str, name: str) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps",
        data={"name": name, "map_kind": "world"},
        files={"file": (f"{name}.png", _png(400, 300), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_region_crud_and_target_resolution(client: TestClient) -> None:
    cid = _demo(client)
    map_id = _upload(client, cid, "Sword Coast")["entity_id"]
    npc = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "npc", "name": "Volo"}
    ).json()

    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps/{map_id}/regions",
        json={
            "name": "Neverwinter Wood", "polygon": [[10, 10], [100, 10], [100, 80]],
            "color": "#3a7", "layer": "political", "target_entity_id": npc["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    region = resp.json()
    assert region["polygon"] == [[10.0, 10.0], [100.0, 10.0], [100.0, 80.0]]
    assert region["target_name"] == "Volo"
    assert region["target_type"] == "npc"

    detail = client.get(f"/api/v1/campaigns/{cid}/maps/{map_id}").json()
    assert len(detail["regions"]) == 1

    moved = client.patch(
        f"/api/v1/campaigns/{cid}/maps/{map_id}/regions/{region['id']}",
        json={"polygon": [[0, 0], [50, 0], [50, 50], [0, 50]], "note": "redrawn"},
    ).json()
    assert len(moved["polygon"]) == 4
    assert moved["note"] == "redrawn"
    assert moved["layer"] == "political"  # untouched by a partial update

    assert client.delete(
        f"/api/v1/campaigns/{cid}/maps/{map_id}/regions/{region['id']}"
    ).status_code == 204
    assert client.get(f"/api/v1/campaigns/{cid}/maps/{map_id}").json()["regions"] == []


def test_polygon_needs_three_points(client: TestClient) -> None:
    cid = _demo(client)
    map_id = _upload(client, cid, "Too Few")["entity_id"]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps/{map_id}/regions", json={"polygon": [[0, 0], [1, 1]]}
    )
    assert resp.status_code == 422


def test_layers_are_collected_from_markers_and_regions(client: TestClient) -> None:
    cid = _demo(client)
    map_id = _upload(client, cid, "Layered")["entity_id"]

    client.post(f"/api/v1/campaigns/{cid}/maps/{map_id}/markers",
                json={"x": 5, "y": 5, "layer": "secrets"})
    client.post(f"/api/v1/campaigns/{cid}/maps/{map_id}/markers", json={"x": 6, "y": 6})
    client.post(f"/api/v1/campaigns/{cid}/maps/{map_id}/regions",
                json={"polygon": [[0, 0], [9, 0], [9, 9]], "layer": "political"})

    detail = client.get(f"/api/v1/campaigns/{cid}/maps/{map_id}").json()
    assert detail["layers"] == ["default", "political", "secrets"]


def test_deleting_a_map_takes_its_regions(client: TestClient) -> None:
    cid = _demo(client)
    map_id = _upload(client, cid, "Doomed")["entity_id"]
    client.post(f"/api/v1/campaigns/{cid}/maps/{map_id}/regions",
                json={"polygon": [[0, 0], [1, 0], [1, 1]]})
    assert client.delete(f"/api/v1/campaigns/{cid}/maps/{map_id}").status_code == 204
    assert client.get(f"/api/v1/campaigns/{cid}/maps/{map_id}").status_code == 404


# --------------------------------------------------------------------------- #
# Archive round-trip
# --------------------------------------------------------------------------- #
def test_quests_survive_a_campaign_export_import(client: TestClient) -> None:
    cid = _demo(client)
    now = client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]
    prereq = _quest(client, cid, "Gather Allies", status="active")["entity_id"]
    later = _quest(client, cid, "Storm the Keep", deadline_game=now + 9000)["entity_id"]
    client.post(f"/api/v1/campaigns/{cid}/quests/{later}/dependencies",
                json={"depends_on_id": prereq})

    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    new_id = client.post("/api/v1/campaigns/import", json=archive).json()["id"]

    quests = client.get(f"/api/v1/campaigns/{new_id}/quests").json()
    by_name = {q["name"]: q for q in quests}
    assert by_name["Gather Allies"]["status"] == "active"
    assert by_name["Storm the Keep"]["depends_on"] == [by_name["Gather Allies"]["entity_id"]]

    # The imported deadline still points at the *imported* quest, not the original.
    events = client.get(f"/api/v1/campaigns/{new_id}/scheduled-events").json()
    assert any(e["title"] == "Deadline: Storm the Keep" for e in events)
    _advance(client, new_id, 9000)
    assert client.get(
        f"/api/v1/campaigns/{new_id}/quests/{by_name['Storm the Keep']['entity_id']}"
    ).json()["status"] == "expired"
