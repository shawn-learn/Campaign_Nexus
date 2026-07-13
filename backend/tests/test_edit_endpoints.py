"""Editing paths added for post-create management: NPC GM notes, timeline hide/delete,
and scheduled-event patching (backend halves of the frontend edit affordances)."""

from __future__ import annotations

from fastapi.testclient import TestClient

DAY = 24 * 3600


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# --------------------------------------------------------------------------- #
# NPC GM notes
# --------------------------------------------------------------------------- #
def test_update_npc_notes(client: TestClient) -> None:
    cid = _demo(client)
    npc = client.post(f"/api/v1/campaigns/{cid}/npcs", json={"name": "Strahd"}).json()
    nid = npc["entity_id"]

    resp = client.patch(
        f"/api/v1/campaigns/{cid}/npcs/{nid}",
        json={"goals": "Reclaim Tatyana", "secrets": "Is a vampire", "voice_notes": "Aristocratic"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["goals"] == "Reclaim Tatyana"
    assert body["secrets"] == "Is a vampire"
    assert body["voice_notes"] == "Aristocratic"

    # Persisted: the list query carries the notes back.
    listed = next(n for n in client.get(f"/api/v1/campaigns/{cid}/npcs").json() if n["entity_id"] == nid)
    assert listed["voice_notes"] == "Aristocratic"


def test_update_npc_missing_404(client: TestClient) -> None:
    cid = _demo(client)
    assert client.patch(f"/api/v1/campaigns/{cid}/npcs/nope", json={"goals": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# Timeline hide / delete
# --------------------------------------------------------------------------- #
def _manual(client: TestClient, cid: str, title: str) -> dict:
    return client.post(
        f"/api/v1/campaigns/{cid}/timeline/manual",
        json={"title": title, "occurred_at_game": 0, "significance": 3},
    ).json()


def test_hide_and_unhide_entry(client: TestClient) -> None:
    cid = _demo(client)
    entry = _manual(client, cid, "A rumor")

    client.patch(f"/api/v1/campaigns/{cid}/timeline/{entry['id']}", json={"is_hidden": True})
    shown = client.get(f"/api/v1/campaigns/{cid}/timeline").json()
    assert all(e["id"] != entry["id"] for e in shown)
    hidden = client.get(f"/api/v1/campaigns/{cid}/timeline", params={"include_hidden": True}).json()
    assert any(e["id"] == entry["id"] and e["is_hidden"] for e in hidden)

    client.patch(f"/api/v1/campaigns/{cid}/timeline/{entry['id']}", json={"is_hidden": False})
    shown = client.get(f"/api/v1/campaigns/{cid}/timeline").json()
    assert any(e["id"] == entry["id"] for e in shown)


def test_delete_manual_entry(client: TestClient) -> None:
    cid = _demo(client)
    entry = _manual(client, cid, "Deletable lore")

    assert client.delete(f"/api/v1/campaigns/{cid}/timeline/{entry['id']}").status_code == 204
    shown = client.get(f"/api/v1/campaigns/{cid}/timeline", params={"include_hidden": True}).json()
    assert all(e["id"] != entry["id"] for e in shown)


def test_delete_projected_entry_is_rejected(client: TestClient) -> None:
    """Projected entries mirror the event log; they may be hidden but not deleted."""
    cid = _demo(client)
    client.post(
        f"/api/v1/campaigns/{cid}/scheduled-events",
        json={"title": "Festival", "fire_at_game": DAY, "action_type": "narrate",
              "action_json": {"text": "The Feast begins."}},
    )
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 2})
    projected = next(
        e for e in client.get(f"/api/v1/campaigns/{cid}/timeline").json() if e["event_id"] is not None
    )
    resp = client.delete(f"/api/v1/campaigns/{cid}/timeline/{projected['id']}")
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Scheduled-event editing
# --------------------------------------------------------------------------- #
def test_update_scheduled_event(client: TestClient) -> None:
    cid = _demo(client)
    ev = client.post(
        f"/api/v1/campaigns/{cid}/scheduled-events",
        json={"title": "Old", "fire_at_game": 2 * DAY, "action_type": "narrate",
              "action_json": {"text": "old text"}},
    ).json()

    resp = client.patch(
        f"/api/v1/campaigns/{cid}/scheduled-events/{ev['id']}",
        json={"title": "New", "fire_at_game": 5 * DAY,
              "action_json": {"text": "new text"}, "recurrence_days": 7},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["title"] == "New"
    assert out["fire_at_game"] == 5 * DAY
    assert out["recurrence_days"] == 7
    assert out["action_json"]["text"] == "new text"


def test_clear_recurrence_via_patch(client: TestClient) -> None:
    cid = _demo(client)
    ev = client.post(
        f"/api/v1/campaigns/{cid}/scheduled-events",
        json={"title": "Weekly", "fire_at_game": DAY, "action_type": "narrate",
              "action_json": {"text": "t"}, "recurrence_days": 7},
    ).json()

    out = client.patch(
        f"/api/v1/campaigns/{cid}/scheduled-events/{ev['id']}", json={"recurrence_days": None}
    ).json()
    assert out["recurrence_days"] is None


def test_update_scheduled_event_missing_404(client: TestClient) -> None:
    cid = _demo(client)
    assert client.patch(
        f"/api/v1/campaigns/{cid}/scheduled-events/nope", json={"title": "x"}
    ).status_code == 404
