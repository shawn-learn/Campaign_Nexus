"""Sprint 6: clock read + manual time advancement across boundaries, audited."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def test_clock_starts_at_epoch(client: TestClient) -> None:
    cid = _demo(client)
    clock = client.get(f"/api/v1/campaigns/{cid}/clock").json()
    assert clock["time_game"] == 0
    assert clock["formatted"]["label"] == "January 1, 1 CE"
    assert clock["formatted"]["weekday"] == "Sunday"


def test_advance_days_updates_clock_and_audits(client: TestClient) -> None:
    cid = _demo(client)
    report = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance",
        json={"days": 3, "reason": "travel"},
    ).json()
    assert report["from_time"] == 0
    assert report["to_time"] == 3 * 24 * 3600
    assert report["formatted"]["label"] == "January 4, 1 CE"

    # Clock persisted and a time_advanced event recorded at the new time.
    clock = client.get(f"/api/v1/campaigns/{cid}/clock").json()
    assert clock["time_game"] == 3 * 24 * 3600
    events = client.get(f"/api/v1/campaigns/{cid}/events").json()
    assert events[0]["event_type"] == "time_advanced"
    assert events[0]["occurred_at_game"] == 3 * 24 * 3600


def test_advance_crosses_month_boundary(client: TestClient) -> None:
    cid = _demo(client)
    # Day 0 is Jan 1; +36 days lands on Feb 6 (Jan has 31 days → day 31 = Feb 1).
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 36})
    clock = client.get(f"/api/v1/campaigns/{cid}/clock").json()
    assert clock["formatted"]["month"] == "February"
    assert clock["formatted"]["day"] == 6


def test_advance_accumulates(client: TestClient) -> None:
    cid = _demo(client)
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"hours": 20})
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"hours": 10})
    clock = client.get(f"/api/v1/campaigns/{cid}/clock").json()
    # 30 hours = 1 day 6 hours.
    assert clock["formatted"]["day"] == 2
    assert clock["formatted"]["time"] == "06:00:00"


def test_zero_advance_rejected(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"reason": "noop"})
    assert resp.status_code == 422
