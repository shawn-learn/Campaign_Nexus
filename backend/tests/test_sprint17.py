"""Sprint 17 — NPC dynamics (FR-6).

The exit criterion is the spec's demo query set, at the bottom of this file:
where is X now / where was X during session 7 / who knows about the artifact /
who has met the party / who is dead.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

DAY = 86_400


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, entity_type: str, name: str) -> str:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": entity_type, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _npc(client: TestClient, cid: str, name: str, **body: object) -> dict:
    resp = client.post(f"/api/v1/campaigns/{cid}/npcs", json={"name": name, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _relocate(client: TestClient, cid: str, npc_id: str, location_id: str, **kw: object) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/npcs/{npc_id}/relocate",
        json={"location_id": location_id, **kw},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _advance(client: TestClient, cid: str, seconds: int) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance", json={"seconds": seconds, "reason": "test"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _clock(client: TestClient, cid: str) -> int:
    return client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"]


# --------------------------------------------------------------------------- #
# Relocation is a projection, not a column you write
# --------------------------------------------------------------------------- #
def test_relocation_projects_location_history_and_the_graph_edge(client: TestClient) -> None:
    cid = _demo(client)
    duskmere = _entity(client, cid, "location", "Duskmere")
    harrowgate = _entity(client, cid, "location", "Harrowgate")
    npc = _npc(client, cid, "Serah Voss", location_id=duskmere)

    assert npc["current_location_id"] == duskmere
    _advance(client, cid, DAY)
    moved = _relocate(client, cid, npc["entity_id"], harrowgate, reason="weekly market")
    assert moved["current_location_id"] == harrowgate
    assert moved["current_location_name"] == "Harrowgate"

    rows = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/history").json()
    assert [r["location_name"] for r in rows] == ["Duskmere", "Harrowgate"]
    # Half-open intervals: the first closes exactly where the second opens.
    assert rows[0]["to_game"] == rows[1]["from_game"]
    assert rows[1]["to_game"] is None  # still there

    # The knowledge graph agrees: exactly one located_at edge, pointing at Harrowgate.
    detail = client.get(f"/api/v1/campaigns/{cid}/entities/{npc['entity_id']}").json()
    located = [link for link in detail["outbound"] if link["link_type"] == "located_at"]
    assert [link["name"] for link in located] == ["Harrowgate"]

    # And the timeline narrates it.
    titles = [t["title"] for t in client.get(f"/api/v1/campaigns/{cid}/timeline").json()]
    assert "Serah Voss traveled from Duskmere to Harrowgate (weekly market)." in titles


def test_relocating_to_the_same_place_is_not_a_fact(client: TestClient) -> None:
    cid = _demo(client)
    inn = _entity(client, cid, "location", "The Rusty Nail")
    npc = _npc(client, cid, "Halda", location_id=inn)
    before = len(client.get(f"/api/v1/campaigns/{cid}/events", params={"limit": 100}).json())

    _relocate(client, cid, npc["entity_id"], inn)
    after = client.get(f"/api/v1/campaigns/{cid}/events", params={"limit": 100}).json()
    assert len(after) == before
    assert len(client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/history").json()) == 1


def test_npc_entity_born_in_the_wiki_gets_its_row(client: TestClient) -> None:
    cid = _demo(client)
    tavern = _entity(client, cid, "location", "Tavern")
    npc_id = _entity(client, cid, "npc", "Wandering Minstrel")
    client.post(f"/api/v1/campaigns/{cid}/entities/{npc_id}/links",
                json={"to_entity": tavern, "link_type_id": "located_at"})

    # The lazy back-fill adopts the existing located_at edge as their current location.
    npc = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}").json()
    assert npc["status"] == "alive"
    assert npc["current_location_id"] == tavern


def test_projection_rebuild_equals_the_incremental_result(client: TestClient, db) -> None:
    """The consistency oracle: replaying the log must re-derive the same NPC state."""
    from scripts.rebuild_projections import rebuild

    cid = _demo(client)
    a = _entity(client, cid, "location", "Alpha")
    b = _entity(client, cid, "location", "Beta")
    npc = _npc(client, cid, "Rambler", location_id=a)
    _advance(client, cid, 3600)
    _relocate(client, cid, npc["entity_id"], b)
    _advance(client, cid, 3600)
    _relocate(client, cid, npc["entity_id"], a)
    client.post(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/interactions", json={})

    before = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}").json()
    history_before = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/history").json()

    rebuild(db, cid)

    after = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}").json()
    history_after = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/history").json()
    assert after["current_location_id"] == before["current_location_id"] == a
    assert after["has_met_party"] is True
    places = [r["location_name"] for r in history_after]
    assert places == [r["location_name"] for r in history_before]
    assert len(history_after) == 3


# --------------------------------------------------------------------------- #
# Itineraries: lazily compiled, fired in the same ordered pass (FR-6.5, docs/07 §9.6)
# --------------------------------------------------------------------------- #
def _daily_route(client: TestClient, cid: str) -> tuple[str, str, str]:
    home = _entity(client, cid, "location", "Cottage")
    market = _entity(client, cid, "location", "Market Square")
    npc = _npc(client, cid, "Baker Tom", location_id=home)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/npcs/{npc['entity_id']}/schedules",
        json={
            "label": "Daily round", "interval_days": 1,
            "stops": [
                {"at_seconds": 8 * 3600, "location_id": market},
                {"at_seconds": 18 * 3600, "location_id": home},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return npc["entity_id"], home, market


def test_a_daily_itinerary_does_not_enqueue_a_year(client: TestClient) -> None:
    cid = _demo(client)
    npc_id, _home, _market = _daily_route(client, cid)

    # Nothing is compiled until the clock is asked to cross a window.
    pending = client.get(f"/api/v1/campaigns/{cid}/scheduled-events").json()
    assert [e for e in pending if e["action_type"] == "move_npc"] == []

    _advance(client, cid, DAY)  # one day → at most the two stops inside it
    moves = [
        e for e in client.get(f"/api/v1/campaigns/{cid}/scheduled-events").json()
        if e["action_type"] == "move_npc"
    ]
    assert 0 < len(moves) <= 2
    assert all(e["status"] == "fired" for e in moves)
    assert client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}").json()["status"] == "alive"


def test_itinerary_moves_the_npc_as_time_passes(client: TestClient) -> None:
    cid = _demo(client)
    npc_id, home, market = _daily_route(client, cid)

    def _at(npc: str) -> str:
        return client.get(f"/api/v1/campaigns/{cid}/npcs/{npc}").json()["current_location_id"]

    _advance(client, cid, 9 * 3600)  # past the 08:00 stop, before the 18:00 one
    assert _at(npc_id) == market

    _advance(client, cid, 10 * 3600)  # past 18:00 → home again
    assert _at(npc_id) == home

    rows = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}/history").json()
    assert [r["location_name"] for r in rows] == ["Cottage", "Market Square", "Cottage"]


def test_preview_shows_itinerary_moves_without_writing(client: TestClient) -> None:
    cid = _demo(client)
    npc_id, _home, _market = _daily_route(client, cid)

    preview = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance/preview", json={"days": 1}
    ).json()
    narratives = [f["narrative"] for f in preview["would_fire"]]
    assert any("Baker Tom would travel to Market Square" in n for n in narratives)
    # A dry run compiles nothing and moves no one.
    assert [
        e for e in client.get(f"/api/v1/campaigns/{cid}/scheduled-events").json()
        if e["action_type"] == "move_npc"
    ] == []
    assert client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}").json()["current_location_id"]


def test_a_dead_npc_ignores_their_itinerary(client: TestClient) -> None:
    cid = _demo(client)
    npc_id, home, _market = _daily_route(client, cid)
    client.post(f"/api/v1/campaigns/{cid}/npcs/{npc_id}/status",
                json={"status": "dead", "reason": "the cellar fire"})

    report = _advance(client, cid, DAY)
    assert any("is dead; the itinerary was skipped" in f["narrative"] for f in report["fired"])
    npc = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}").json()
    assert npc["current_location_id"] == home  # they never left the cottage


def test_deleting_a_schedule_retracts_its_pending_occurrences(client: TestClient) -> None:
    cid = _demo(client)
    npc_id, _home, _market = _daily_route(client, cid)
    schedule = client.get(f"/api/v1/campaigns/{cid}/npcs/{npc_id}/schedules").json()[0]

    client.post(f"/api/v1/campaigns/{cid}/clock/advance/preview", json={"days": 1})
    assert client.delete(
        f"/api/v1/campaigns/{cid}/npcs/schedules/{schedule['id']}"
    ).status_code == 204

    report = _advance(client, cid, DAY)
    assert not any("Baker Tom" in f["narrative"] for f in report["fired"])


# --------------------------------------------------------------------------- #
# The demo query set (the sprint's exit criterion)
# --------------------------------------------------------------------------- #
def test_the_spec_query_set(client: TestClient) -> None:
    cid = _demo(client)
    duskmere = _entity(client, cid, "location", "Duskmere")
    harrowgate = _entity(client, cid, "location", "Harrowgate")
    artifact = _entity(client, cid, "item", "The Sunken Crown")

    serah = _npc(client, cid, "Serah Voss", location_id=duskmere)["entity_id"]
    grim = _npc(client, cid, "Grim Halloway", location_id=harrowgate)["entity_id"]
    ghost = _npc(client, cid, "Old Ghost", location_id=duskmere)["entity_id"]

    # Two NPCs know about the artifact; one has met the party; one is dead.
    for npc in (serah, grim):
        client.post(f"/api/v1/campaigns/{cid}/entities/{npc}/links",
                    json={"to_entity": artifact, "link_type_id": "knows_about"})
    client.post(f"/api/v1/campaigns/{cid}/npcs/{serah}/interactions",
                json={"summary": "haggled over the map"})
    client.post(f"/api/v1/campaigns/{cid}/npcs/{ghost}/status", json={"status": "dead"})

    # Session 7 runs while Serah is in Duskmere, then she leaves before it ends.
    session_id = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/sessions/{session_id}/start")
    _advance(client, cid, 3600)
    _relocate(client, cid, serah, harrowgate, reason="fleeing")
    _advance(client, cid, 3600)
    client.post(f"/api/v1/campaigns/{cid}/sessions/{session_id}/end")
    _advance(client, cid, DAY)
    _relocate(client, cid, serah, duskmere, reason="returning home")

    # 1. Where is X now?
    now = client.get(f"/api/v1/campaigns/{cid}/npcs/{serah}/where").json()
    assert [p["location_name"] for p in now["places"]] == ["Duskmere"]
    assert now["places"][0]["to_game"] is None

    # 2. Where was X during session 7? (a span → every place she occupied while it ran)
    during = client.get(
        f"/api/v1/campaigns/{cid}/npcs/{serah}/where", params={"session_id": session_id}
    ).json()
    assert [p["location_name"] for p in during["places"]] == ["Duskmere", "Harrowgate"]
    assert during["session_id"] == session_id

    # 2b. Where was X at one instant? (exactly one row)
    at = client.get(
        f"/api/v1/campaigns/{cid}/npcs/{serah}/where", params={"at_game": _clock(client, cid) - DAY}
    ).json()
    assert [p["location_name"] for p in at["places"]] == ["Harrowgate"]

    # 3. Who knows about the artifact?
    knowers = client.get(f"/api/v1/campaigns/{cid}/npcs", params={"knows": artifact}).json()
    assert sorted(n["name"] for n in knowers) == ["Grim Halloway", "Serah Voss"]

    # 4. Who has met the party?
    met = client.get(f"/api/v1/campaigns/{cid}/npcs", params={"met_party": True}).json()
    assert [n["name"] for n in met] == ["Serah Voss"]
    assert met[0]["last_party_interaction_game"] is not None

    # 5. Who is dead?
    dead = client.get(f"/api/v1/campaigns/{cid}/npcs", params={"status": "dead"}).json()
    assert [n["name"] for n in dead] == ["Old Ghost"]

    # ...and the bonus: who is in Duskmere right now?
    here = client.get(f"/api/v1/campaigns/{cid}/npcs", params={"location_id": duskmere}).json()
    assert sorted(n["name"] for n in here) == ["Old Ghost", "Serah Voss"]


def test_npcs_survive_a_campaign_export_import(client: TestClient) -> None:
    cid = _demo(client)
    home = _entity(client, cid, "location", "Home")
    away = _entity(client, cid, "location", "Away")
    npc = _npc(client, cid, "Traveller", location_id=home)["entity_id"]
    _advance(client, cid, 3600)
    _relocate(client, cid, npc, away)

    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    new_id = client.post("/api/v1/campaigns/import", json=archive).json()["id"]

    imported = client.get(f"/api/v1/campaigns/{new_id}/npcs").json()
    traveller = next(n for n in imported if n["name"] == "Traveller")
    assert traveller["current_location_name"] == "Away"
    rows = client.get(f"/api/v1/campaigns/{new_id}/npcs/{traveller['entity_id']}/history").json()
    assert [r["location_name"] for r in rows] == ["Home", "Away"]


# --------------------------------------------------------------------------- #
# Travel planner (FR-5.3, docs/07 §9.5)
# --------------------------------------------------------------------------- #
def test_travel_preview_costs_the_route_and_writes_nothing(client: TestClient) -> None:
    cid = _demo(client)
    keep = _entity(client, cid, "location", "Blackreach Keep")
    before = _clock(client, cid)

    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 24, "terrain": "road", "pace": "normal", "conveyance": "foot",
             "to_location_id": keep},
        ]},
    ).json()

    # 24 miles at 24 miles/travel-day on a road = exactly one 8-hour travel day.
    assert plan["travel_seconds"] == 8 * 3600
    assert plan["rest_stops"] == 0
    assert plan["distance_unit"] == "miles"
    assert plan["destination_name"] == "Blackreach Keep"
    assert _clock(client, cid) == before  # dry run


def test_forest_halves_the_pace(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [{"distance": 24, "terrain": "forest"}]},
    ).json()
    assert plan["travel_seconds"] == 16 * 3600  # half speed → twice as long


def test_multi_day_travel_inserts_overnight_long_rests(client: TestClient) -> None:
    cid = _demo(client)
    town = _entity(client, cid, "location", "Farhaven")
    start = _clock(client, cid)

    body = {"legs": [{"distance": 48, "terrain": "road", "to_location_id": town}]}
    plan = client.post(f"/api/v1/campaigns/{cid}/party/travel/preview", json=body).json()
    assert plan["travel_seconds"] == 16 * 3600  # two travel days
    assert plan["rest_stops"] == 1              # one night on the road
    assert plan["total_seconds"] == 16 * 3600 + 28800

    result = client.post(f"/api/v1/campaigns/{cid}/party/travel", json=body).json()
    assert result["rest_stops"] == 1
    assert result["to_time"] - start == plan["total_seconds"]
    assert _clock(client, cid) == result["to_time"]

    party = client.get(f"/api/v1/campaigns/{cid}/party").json()
    assert party["current_location_name"] == "Farhaven"

    timeline = client.get(f"/api/v1/campaigns/{cid}/timeline").json()
    titles = [t["title"] for t in timeline]
    assert "The party traveled to Farhaven." in titles
    assert "The party arrived at Farhaven." in titles
    # The rests the planner inserted on the GM's behalf are visible as story, not silent.
    assert [t["title"] for t in timeline].count("The party completed a long rest.") == 1


def test_travel_narrates_unnamed_legs_by_distance(client: TestClient) -> None:
    cid = _demo(client)
    client.post(f"/api/v1/campaigns/{cid}/party/travel",
                json={"legs": [{"distance": 12, "terrain": "road"}], "forced_march": True})
    titles = [t["title"] for t in client.get(f"/api/v1/campaigns/{cid}/timeline").json()]
    assert "The party traveled 12 miles by forced march." in titles


def test_forced_march_skips_the_rest_stops(client: TestClient) -> None:
    cid = _demo(client)
    start = _clock(client, cid)
    body = {"legs": [{"distance": 48, "terrain": "road"}], "forced_march": True}

    result = client.post(f"/api/v1/campaigns/{cid}/party/travel", json=body).json()
    assert result["rest_stops"] == 0
    assert result["to_time"] - start == 16 * 3600


def test_travel_preview_shows_what_fires_en_route(client: TestClient) -> None:
    cid = _demo(client)
    now = _clock(client, cid)
    client.post(f"/api/v1/campaigns/{cid}/scheduled-events", json={
        "title": "The Midsummer Festival", "fire_at_game": now + 4 * 3600,
        "action_type": "narrate", "action_json": {"text": "Bells ring out across the valley."},
    })

    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [{"distance": 24, "terrain": "road"}]},
    ).json()
    assert any("Bells ring out" in f["narrative"] for f in plan["would_fire"])


def test_travel_rejects_an_unknown_vocabulary(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [{"distance": 10, "terrain": "the astral sea"}]},
    )
    assert resp.status_code == 422
    assert "the astral sea" in resp.json()["detail"]


def test_a_system_without_travel_rules_says_so(client: TestClient) -> None:
    """simpletest ships no pace table — the planner must degrade, not guess (§10.8)."""
    cid = client.post("/api/v1/campaigns", json={
        "name": "Rules-light", "rule_system_id": "simpletest",
    }).json()["id"]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [{"distance": 10}]},
    )
    assert resp.status_code == 501
    assert "no travel rules" in resp.json()["detail"]
