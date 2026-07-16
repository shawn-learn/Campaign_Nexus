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


def test_cos_full_moon_scheduling_and_firing(client: TestClient) -> None:
    # 1. Create a campaign with the Barovian calendar preset
    resp = client.post("/api/v1/campaigns", json={"name": "Moon Test", "calendar_id": "barovian"})
    assert resp.status_code == 201
    cid = resp.json()["id"]

    # 2. Check scheduled-events: one should be the first full moon
    events_resp = client.get(f"/api/v1/campaigns/{cid}/scheduled-events")
    assert events_resp.status_code == 200
    events = events_resp.json()

    full_moon_events = [e for e in events if e["action_type"] == "cos_full_moon"]
    assert len(full_moon_events) == 1
    fm_event = full_moon_events[0]
    assert fm_event["title"] == "Full Moon"
    assert fm_event["recurrence_days"] == 30
    assert fm_event["status"] == "pending"

    # Expected time is 14 days and 20 hours (1281600 seconds)
    expected_fire_at = 14 * 24 * 3600 + 20 * 3600  # 1281600
    assert fm_event["fire_at_game"] == expected_fire_at

    # 3. Verify is_full_moon is not set yet
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert "is_full_moon" not in flags

    # 4. Advance time past the full moon rise (e.g. 15 days, wait)
    # The clock starts at 0. So advancing by 15 days will cross the 14d 20h mark.
    advance_resp = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance",
        json={"days": 15, "reason": "wait"}
    )
    assert advance_resp.status_code == 200
    report = advance_resp.json()

    # 5. Verify the full moon fired
    fired_fm = [f for f in report["fired"] if f["title"] == "Full Moon"]
    assert len(fired_fm) == 1
    assert "The full moon rises" in fired_fm[0]["narrative"]

    # 6. Verify is_full_moon flag is set to True
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert flags.get("is_full_moon") is True

    # 7. Check that the dawn clearing event "Full Moon Ends" was scheduled at dawn (14 days, 20 hours + 10 hours = 15 days, 6 hours)
    events_resp = client.get(f"/api/v1/campaigns/{cid}/scheduled-events?status_filter=pending")
    events = events_resp.json()

    end_events = [e for e in events if e["title"] == "Full Moon Ends"]
    assert len(end_events) == 1
    assert end_events[0]["fire_at_game"] == expected_fire_at + 10 * 3600

    # 8. Advance time past dawn (e.g. advance by 1 day)
    advance_resp = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance",
        json={"days": 1, "reason": "wait"}
    )
    assert advance_resp.status_code == 200
    report = advance_resp.json()

    # 9. Verify the dawn clearing event fired
    fired_end = [f for f in report["fired"] if f["title"] == "Full Moon Ends"]
    assert len(fired_end) == 1

    # 10. Verify flag is now False
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert flags.get("is_full_moon") is False

    # 11. Verify that the next full moon is scheduled for day 44 (1281600 + 30 days)
    events_resp = client.get(f"/api/v1/campaigns/{cid}/scheduled-events?status_filter=pending")
    events = events_resp.json()
    full_moon_events = [e for e in events if e["action_type"] == "cos_full_moon"]
    assert len(full_moon_events) == 1
    assert full_moon_events[0]["fire_at_game"] == expected_fire_at + 30 * 24 * 3600


