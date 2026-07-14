from __future__ import annotations

from fastapi.testclient import TestClient

DAY = 24 * 3600

def test_barovian_calendar_creation(client: TestClient) -> None:
    # 1. Create a campaign with the Barovian calendar preset
    resp = client.post("/api/v1/campaigns", json={"name": "Strahd Test", "calendar_id": "barovian"})
    assert resp.status_code == 201
    cid = resp.json()["id"]

    # 2. Verify clock starts at 735 BC Lunas 1
    clock = client.get(f"/api/v1/campaigns/{cid}/clock").json()
    assert clock["time_game"] == 0
    # Wait, the frontend gets calendar json and parses it, let's verify custom preset is loaded
    assert clock["calendar"]["id"] == "barovian"
    assert clock["calendar"]["start_year"] == 735
    assert clock["calendar"]["epoch_label"] == "BC"

def test_barovian_weather_roll(client: TestClient) -> None:
    resp = client.post("/api/v1/campaigns", json={"name": "Weather Test", "calendar_id": "barovian"})
    cid = resp.json()["id"]

    # 1. Schedule a weather roll event directly in the database (bypassing the user-facing POST API constraints)
    from app.core.db import SessionLocal
    from app.modules.time.models import ScheduledEvent
    
    with SessionLocal() as session:
        event = ScheduledEvent(
            id="test-weather-event",
            campaign_id=cid,
            fire_at_game=28800,  # 8 AM
            recurrence_days=1,
            action_type="cos_weather_roll",
            action_json="{}",
            title="Daily Weather",
            created_by_kind="gm",
            status="pending"
        )
        session.add(event)
        session.commit()

    # 2. Advance time past 8 AM (e.g. 1 day)
    advance_resp = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance",
        json={"days": 1, "reason": "wait"}
    )
    assert advance_resp.status_code == 200
    report = advance_resp.json()

    # 3. Verify event fired
    assert len(report["fired"]) == 1
    assert "Weather Update:" in report["fired"][0]["narrative"]

    # 4. Verify flags were populated in the database
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert "weather_temperature_c" in flags
    assert "weather_wind" in flags
    assert "weather_precipitation" in flags
    assert "weather_mist_thickness" in flags

def test_manual_weather_roll(client: TestClient) -> None:
    resp = client.post("/api/v1/campaigns", json={"name": "Manual Roll Test", "calendar_id": "barovian"})
    cid = resp.json()["id"]

    # Trigger manual weather roll endpoint
    roll_resp = client.post(f"/api/v1/campaigns/{cid}/weather/roll")
    assert roll_resp.status_code == 200
    res = roll_resp.json()
    assert "narrative" in res
    assert "mist" in res
    assert "wind" in res

    # Verify flags were set
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert flags["weather_mist_thickness"] == res["mist"]

