"""Sprint 9: rules plugin interface, simpletest, stat-block validate/derive round-trip."""

from __future__ import annotations

import pytest
from app.modules.rules import registry
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# --- plugin conformance kit (parameterized over every installed system) -----
@pytest.mark.parametrize("system", registry.all_systems(), ids=lambda s: s.id)
def test_plugin_conformance(system) -> None:
    assert system.id and system.name and system.version
    for sheet_type in system.sheet_types():
        schema = system.sheet_schema(sheet_type)
        assert schema.get("type") == "object"
        layout = system.render_layout(sheet_type)
        assert isinstance(layout.get("sections"), list) and layout["sections"]
        for section in layout["sections"]:
            for field in section["fields"]:
                # The generic renderer cannot guess a system's attribute names (5e has six,
                # Nimble four), so an ability-array must name its own sub-keys.
                if field["role"] == "ability-array":
                    assert field.get("keys"), f"{system.id}/{sheet_type}: {field['key']}"
        # A valid empty-ish doc round-trips through validate/derive without exploding.
        assert isinstance(system.validate(sheet_type, {}), list)

        # Live-play facade: the playbook relies on these for *every* system (docs/04 §6.8).
        status = system.initial_status(sheet_type, {})
        assert isinstance(status, dict)
        profile = system.combat_profile(sheet_type, {}, status)
        assert {"max_hp", "hp", "initiative"} <= profile.keys()
        assert all(isinstance(profile[k], int) for k in ("max_hp", "hp", "initiative"))

    # Rests: whatever they are called, they must be durable and self-consistent.
    rests = system.rest_types()
    assert isinstance(rests, list)
    for rest_type in rests:
        assert system.rest_duration_seconds(rest_type) > 0
        assert isinstance(system.apply_rest(rest_type, {}, {}), dict)
    overnight = system.overnight_rest_type()
    assert overnight is None or overnight in rests

    assert system.round_length_seconds() > 0
    assert isinstance(system.travel_pace_table().get("supported"), bool)


def test_rule_systems_listed(client: TestClient) -> None:
    systems = client.get("/api/v1/rule-systems").json()
    ids = {s["id"] for s in systems}
    assert "simpletest" in ids
    st = next(s for s in systems if s["id"] == "simpletest")
    assert set(st["sheet_types"]) == {"pc", "npc", "monster"}


def test_schema_and_layout_endpoints(client: TestClient) -> None:
    schema = client.get("/api/v1/rule-systems/simpletest/schema/pc").json()
    assert "level" in schema["properties"]
    layout = client.get("/api/v1/rule-systems/simpletest/layout/pc").json()
    assert layout["sections"][0]["title"] == "Vitals"


def test_validate_endpoint_reports_errors(client: TestClient) -> None:
    ok = client.post(
        "/api/v1/rule-systems/simpletest/validate",
        json={"sheet_type": "pc", "doc": {"level": 3, "hit_points": 24, "armor_class": 15}},
    ).json()
    assert ok["valid"] is True
    assert ok["derived"]["proficiency_bonus"] == 2  # (3-1)//4 + 2
    assert ok["derived"]["power_level"] == 3 + 24 // 10

    bad = client.post(
        "/api/v1/rule-systems/simpletest/validate",
        json={"sheet_type": "pc", "doc": {"level": 99}},  # over max, missing required
    ).json()
    assert bad["valid"] is False and bad["errors"]


def test_stat_block_create_validate_derive_roundtrip(client: TestClient) -> None:
    cid = _demo(client)
    created = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "simpletest", "sheet_type": "pc", "label": "Serah",
              "doc": {"level": 5, "hit_points": 40, "armor_class": 16}},
    )
    assert created.status_code == 201, created.text
    block = created.json()
    assert block["derived"]["power_level"] == 5 + 4  # 40//10
    assert block["schema_version"] == "1.0.0"

    # Edit updates derived values.
    updated = client.put(
        f"/api/v1/campaigns/{cid}/stat-blocks/{block['id']}",
        json={"doc": {"level": 10, "hit_points": 80, "armor_class": 18}},
    ).json()
    assert updated["derived"]["proficiency_bonus"] == 4  # (10-1)//4 + 2
    assert updated["derived"]["power_level"] == 10 + 8


def test_invalid_stat_block_rejected_with_errors(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "simpletest", "sheet_type": "pc",
              "doc": {"hit_points": 10}},  # missing required level/armor_class
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"]


def test_unknown_system_rejected(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "pathfinder", "sheet_type": "pc", "doc": {}},
    )
    assert resp.status_code == 404
