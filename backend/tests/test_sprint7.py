"""Sprint 7: scheduled events fire in order during advancement; preview; set_flag; recurrence."""

from __future__ import annotations

from fastapi.testclient import TestClient

DAY = 24 * 3600


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _schedule(client: TestClient, cid: str, **body):
    return client.post(f"/api/v1/campaigns/{cid}/scheduled-events", json=body)


def test_one_shot_narrate_fires_and_lands_on_timeline(client: TestClient) -> None:
    cid = _demo(client)
    _schedule(
        client, cid, title="Festival begins", fire_at_game=2 * DAY,
        action_type="narrate", action_json={"text": "The Feast of Lanterns begins."},
    )
    report = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 5, "reason": "downtime"}
    ).json()
    assert [f["narrative"] for f in report["fired"]] == ["The Feast of Lanterns begins."]

    # It became a world_event in the log, stamped at its fire time (day 2), before time_advanced.
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert types[0] == "time_advanced" and "world_event" in types


def test_weekly_festival_fires_four_times_in_order(client: TestClient) -> None:
    """The roadmap exit criterion: advancing 30 days fires a weekly event 4x, in order."""
    cid = _demo(client)
    _schedule(
        client, cid, title="Market day", fire_at_game=7 * DAY,
        action_type="narrate", action_json={"text": "Market day."}, recurrence_days=7,
    )
    report = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 30}
    ).json()
    fire_days = [f["at_time"] // DAY for f in report["fired"]]
    assert fire_days == [7, 14, 21, 28]  # in chronological order

    # The recurring event remains pending, now scheduled for day 35.
    pending = client.get(
        f"/api/v1/campaigns/{cid}/scheduled-events", params={"status_filter": "pending"}
    ).json()
    assert pending[0]["fire_at_game"] == 35 * DAY


def test_preview_matches_without_committing(client: TestClient) -> None:
    cid = _demo(client)
    _schedule(
        client, cid, title="Market day", fire_at_game=7 * DAY,
        action_type="narrate", action_json={"text": "Market day."}, recurrence_days=7,
    )
    preview = client.post(
        f"/api/v1/campaigns/{cid}/clock/advance/preview", json={"days": 30}
    ).json()
    assert [f["at_time"] // DAY for f in preview["would_fire"]] == [7, 14, 21, 28]

    # Preview did not move the clock.
    assert client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"] == 0


def test_set_flag_action_updates_state(client: TestClient) -> None:
    cid = _demo(client)
    _schedule(
        client, cid, title="Merchant dies", fire_at_game=DAY,
        action_type="set_flag", action_json={"key": "merchant_alive", "value": False},
    )
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 2})
    flags = client.get(f"/api/v1/campaigns/{cid}/flags").json()
    assert flags == {"merchant_alive": False}
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "flag_changed" in types


def test_cancelled_event_does_not_fire(client: TestClient) -> None:
    cid = _demo(client)
    ev = _schedule(
        client, cid, title="Cancelled", fire_at_game=DAY, action_type="narrate",
    ).json()
    client.delete(f"/api/v1/campaigns/{cid}/scheduled-events/{ev['id']}")
    report = client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 3}).json()
    assert report["fired"] == []


def test_future_event_not_yet_due(client: TestClient) -> None:
    cid = _demo(client)
    _schedule(client, cid, title="Later", fire_at_game=100 * DAY, action_type="narrate")
    report = client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 3}).json()
    assert report["fired"] == []
