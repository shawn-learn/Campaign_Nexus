"""Skill challenges (FR-12): a system-agnostic, graduated non-combat scene resolved by a
run of skill checks. Modelled on the CoS "Choking Fog" challenge (5 checks, 0 to 5 failures
mapping to escalating outcomes)."""

from __future__ import annotations

from app.modules.rules import registry
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# The "Choking Fog" outcome ladder, condensed to what the mechanic needs.
_FOG = {
    "name": "The Choking Fog",
    "premise": "The mists tighten, spiraling upward like a living wall of grey.",
    "total_checks": 5,
    "approaches": [
        {"skill": "Perception", "difficulty": "easy", "hint": "Detect the unnatural stillness"},
        {"skill": "Survival", "difficulty": "normal", "hint": "Hold a straight line"},
        {"skill": "Arcana", "difficulty": "hard", "hint": "Identify planar distortion"},
    ],
    "outcomes": [
        {"min_failures": 0, "label": "Exceptional Success", "effects": ["Spot wolves early"]},
        {"min_failures": 1, "label": "Strong Success", "effects": ["Normal Wolf Ambush"]},
        {"min_failures": 2, "label": "Minor Complication", "effects": ["Out of formation"]},
        {"min_failures": 3, "label": "Moderate Consequence", "effects": ["Wolves +1 damage"]},
        {"min_failures": 4, "label": "Severe Consequence", "effects": ["Party Slowed"]},
        {"min_failures": 5, "label": "Catastrophic Consequence", "effects": ["Surrounded"]},
    ],
}


def _create_fog(client: TestClient, cid: str) -> dict:
    resp = client.post(f"/api/v1/campaigns/{cid}/skill-challenges", json=_FOG)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- plugin DC hook is system-specific -------------------------------------
def test_dc_ladder_differs_across_systems() -> None:
    assert registry.get_system("dnd5e").skill_check_dcs()["hard"] == 20
    assert registry.get_system("nimble").skill_check_dcs()["hard"] == 15


def test_create_exposes_system_dcs(client: TestClient) -> None:
    cid = _demo(client)  # demo campaign is 5e
    ch = _create_fog(client, cid)
    assert ch["name"] == "The Choking Fog"
    assert ch["dcs"]["easy"] == 10 and ch["dcs"]["hard"] == 20
    assert len(ch["approaches"]) == 3 and len(ch["outcomes"]) == 6
    # It's a wiki entity, so it appears in the registry and can be linked.
    listed = client.get(
        f"/api/v1/campaigns/{cid}/entities?entity_type=skill_challenge").json()
    assert any(e["id"] == ch["id"] for e in listed)


# --- graduated resolution --------------------------------------------------
def _record(client: TestClient, cid: str, run_id: str, outcome: str) -> dict:
    return client.post(
        f"/api/v1/campaigns/{cid}/skill-runs/{run_id}/checks",
        json={"skill": "Perception", "difficulty": "normal", "outcome": outcome},
    ).json()


def test_clean_run_resolves_to_exceptional_success(client: TestClient) -> None:
    cid = _demo(client)
    ch = _create_fog(client, cid)
    run = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": ch["id"]}
    ).json()
    state = run
    for _ in range(5):
        state = _record(client, cid, run["run_id"], "success")
    assert state["resolved"] is True
    assert state["successes"] == 5 and state["failures"] == 0
    assert state["checks_remaining"] == 0
    assert state["outcome"]["label"] == "Exceptional Success"


def test_three_failures_selects_moderate_tier(client: TestClient) -> None:
    cid = _demo(client)
    ch = _create_fog(client, cid)
    run = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": ch["id"]}
    ).json()["run_id"]
    for outcome in ("failure", "success", "failure", "success", "critical_failure"):
        state = _record(client, cid, run, outcome)
    assert state["failures"] == 3 and state["successes"] == 2
    assert state["resolved"] is True
    assert state["outcome"]["label"] == "Moderate Consequence"  # min_failures == 3


def test_dc_is_stamped_from_plugin_and_overridable(client: TestClient) -> None:
    cid = _demo(client)
    ch = _create_fog(client, cid)
    run = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": ch["id"]}
    ).json()["run_id"]
    state = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs/{run}/checks",
        json={"skill": "Arcana", "difficulty": "hard", "outcome": "success"},
    ).json()
    assert state["checks"][0]["dc"] == 20  # 5e "hard"
    state = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs/{run}/checks",
        json={"skill": "Insight", "difficulty": "normal", "outcome": "success", "dc": 13},
    ).json()
    assert state["checks"][1]["dc"] == 13  # ad-hoc override wins


def test_undo_reopens_a_resolved_run(client: TestClient) -> None:
    cid = _demo(client)
    ch = _create_fog(client, cid)
    run = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": ch["id"]}
    ).json()["run_id"]
    for _ in range(5):
        state = _record(client, cid, run, "success")
    assert state["resolved"] is True
    # Recording into a resolved run is a conflict...
    assert client.post(
        f"/api/v1/campaigns/{cid}/skill-runs/{run}/checks",
        json={"skill": "x", "difficulty": "normal", "outcome": "success"},
    ).status_code == 409
    # ...but undo pops the last check and re-opens it.
    state = client.post(f"/api/v1/campaigns/{cid}/skill-runs/{run}/undo").json()
    assert state["resolved"] is False and state["checks_made"] == 4


def test_race_mode_resolves_on_failure_cap(client: TestClient) -> None:
    cid = _demo(client)
    ch = client.post(
        f"/api/v1/campaigns/{cid}/skill-challenges",
        json={"name": "Ritual Race", "failure_cap": 3, "success_target": 4,
              "outcomes": [{"min_failures": 0, "label": "Sealed"},
                           {"min_failures": 3, "label": "Unleashed"}]},
    ).json()
    run = client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": ch["id"]}
    ).json()["run_id"]
    for outcome in ("failure", "success", "failure", "failure"):
        state = _record(client, cid, run, outcome)
    assert state["failures"] == 3 and state["resolved"] is True
    assert state["outcome"]["label"] == "Unleashed"
    assert state["checks_remaining"] is None  # race mode has no fixed length


def test_unknown_challenge_404s_on_run_start(client: TestClient) -> None:
    cid = _demo(client)
    assert client.post(
        f"/api/v1/campaigns/{cid}/skill-runs", json={"challenge_id": "nope"}
    ).status_code == 404
