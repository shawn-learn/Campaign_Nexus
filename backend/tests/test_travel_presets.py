from __future__ import annotations

from fastapi.testclient import TestClient

def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]

def _entity(client: TestClient, cid: str, entity_type: str, name: str) -> str:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": entity_type, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]

def test_travel_presets_normal(client: TestClient) -> None:
    cid = _demo(client)
    keep = _entity(client, cid, "location", "Blackreach Keep")

    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 24, "terrain": "road", "travel_type": "normal", "to_location_id": keep},
        ]},
    ).json()

    # 24 miles at 24 miles/day = exactly one 8-hour travel day.
    assert plan["travel_seconds"] == 8 * 3600
    assert plan["rest_stops"] == 0
    assert plan["distance_unit"] == "miles"
    assert plan["destination_name"] == "Blackreach Keep"

def test_travel_presets_difficult_terrain(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 24, "terrain": "road", "travel_type": "difficult terrain"},
        ]},
    ).json()

    # Difficult terrain halves speed (takes double time) -> 16 hours.
    assert plan["travel_seconds"] == 16 * 3600

def test_travel_presets_slow_sneak(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 18, "terrain": "road", "travel_type": "slow (sneak)"},
        ]},
    ).json()

    # Slow pace covers 18 miles in 8 hours.
    assert plan["travel_seconds"] == 8 * 3600

def test_travel_presets_mounted(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 40, "terrain": "road", "travel_type": "mounted"},
        ]},
    ).json()

    # Mounted horse daily speed is 40 miles/8 hours.
    assert plan["travel_seconds"] == 8 * 3600

def test_travel_presets_gallop_difficult_terrain(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 20, "terrain": "road", "travel_type": "gallop difficult terrain"},
        ]},
    ).json()

    # Mounted speed is 40 miles/day. Difficult terrain halves speed to 20 miles/day.
    # Normal duration for 20 miles is 8 hours (28800 seconds).
    # Gallop saves 1 hour (3600 seconds) since 8 hours >= 2 hours.
    # Expected duration: 7 hours.
    assert plan["travel_seconds"] == 7 * 3600

def test_travel_presets_forced_march_saves(client: TestClient) -> None:
    cid = _demo(client)
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 48, "terrain": "road", "travel_type": "forced march"},
        ]},
    ).json()

    # 48 miles at 24 miles/day = 16 hours.
    # Since it is a forced march, it has 0 rest stops.
    assert plan["travel_seconds"] == 16 * 3600
    assert plan["rest_stops"] == 0
    assert plan["forced_march"] is True
    
    # Constitution saves for hours 9 through 16 (8 saves)
    saves = plan["forced_march_saves"]
    assert len(saves) == 8
    assert saves[0]["hour"] == 9
    assert saves[0]["dc"] == 11
    assert saves[-1]["hour"] == 16
    assert saves[-1]["dc"] == 18

def test_forced_march_saves_reset_each_day(client: TestClient) -> None:
    cid = _demo(client)
    # 120 miles at 24 miles/day = 40 hours of continuous forced march (~1.67 days).
    plan = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 120, "terrain": "road", "travel_type": "forced march"},
        ]},
    ).json()

    assert plan["travel_seconds"] == 40 * 3600
    saves = plan["forced_march_saves"]

    # Day 1: hours 9..24 (16 saves, DC 11..26). Day 2: cumulative hours 33..40
    # (hours 9..16 of day 2, DC 11..18) — the DC RESETS at the day boundary.
    assert len(saves) == (24 - 8) + (16 - 8)  # 24 saves total
    day1 = [s for s in saves if s["day"] == 1]
    day2 = [s for s in saves if s["day"] == 2]
    assert day1[0]["hour"] == 9 and day1[0]["dc"] == 11
    assert day1[-1]["hour"] == 24 and day1[-1]["dc"] == 26
    # Day 2 starts fresh: hour 33 is the 9th hour of day 2, back to DC 11.
    assert day2[0]["hour"] == 33 and day2[0]["dc"] == 11
    assert day2[-1]["hour"] == 40 and day2[-1]["dc"] == 18
    assert max(s["dc"] for s in day2) < max(s["dc"] for s in day1)


def test_travel_rejects_cross_campaign_waypoint(client: TestClient) -> None:
    cid = _demo(client)
    # A second campaign whose location must not be reachable as a waypoint.
    other = client.post("/api/v1/campaigns", json={"name": "Other Realm"}).json()["id"]
    foreign = _entity(client, other, "location", "Secret Fortress")

    resp = client.post(
        f"/api/v1/campaigns/{cid}/party/travel/preview",
        json={"legs": [
            {"distance": 10, "terrain": "road", "to_location_id": foreign},
        ]},
    )
    assert resp.status_code == 422, resp.text
    assert "not found in this campaign" in resp.json()["detail"]


def test_travel_presets_commit_notification(client: TestClient) -> None:
    cid = _demo(client)
    keep = _entity(client, cid, "location", "Keep")

    commit = client.post(
        f"/api/v1/campaigns/{cid}/party/travel",
        json={"legs": [
            {"distance": 24, "terrain": "road", "travel_type": "mounted", "to_location_id": keep},
        ]},
    ).json()

    # Verify a notification event was fired
    events = client.get(f"/api/v1/campaigns/{cid}/scheduled-events?status_filter=fired").json()
    travel_rules_events = [e for e in events if e["title"] == "Travel Rules Applied"]
    assert len(travel_rules_events) > 0
    
    desc = travel_rules_events[0]["description"]
    assert "Mounted Travel:" in desc
