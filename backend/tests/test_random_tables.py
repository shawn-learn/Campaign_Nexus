"""Random tables (FR-12.x): entity-backed roll tables whose rows can link to other entities
(e.g. a CoS "random encounters" table where each row runs an encounter)."""

from __future__ import annotations

import pytest
from app.modules.playbook import tables
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# --- pure selection logic (no randomness) ----------------------------------
def test_dice_spec_passes_notation_through_and_flags_weighted() -> None:
    # Notation itself is app.core.dice's job (see test_dice.py); this is the table-specific
    # part — the "" sentinel that selects weighted mode instead of a range roll.
    assert tables.dice_spec("1d20") == "1d20"
    assert tables.dice_spec("d12+d8") == "d12+d8"
    assert tables.dice_spec("2d6 + 1d4") == "2d6 + 1d4"
    assert tables.dice_spec("") is None  # weighted mode
    assert tables.dice_spec("   ") is None


def test_dice_spec_reraises_bad_notation_as_bad_dice() -> None:
    # The router maps BadDice to a 422; a leaked BadExpression would 500 instead.
    for bad in ["2x6", "1d", "abc", "1d20++5"]:
        with pytest.raises(tables.BadDice):
            tables.dice_spec(bad)


def test_d12_plus_d8_table_rolls_in_2_to_20(client: TestClient) -> None:
    cid = _demo(client)
    rows = [{"min": n, "max": n, "text": f"result {n}"} for n in range(2, 21)]
    table = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={"name": "Barovia Encounters", "dice": "d12+d8", "rows": rows},
    ).json()
    for _ in range(60):
        r = client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").json()
        assert 2 <= r["roll"] <= 20  # d12+d8 spans 2..20
        assert r["index"] is not None


def test_table_with_a_flat_modifier_rolls_in_range(client: TestClient) -> None:
    # Modifiers used to 400: the old NdM-only parser rejected the "+3" term. Now that dice
    # notation comes from app.core.dice, "2d6+3" spans 5..15 and validates against it.
    cid = _demo(client)
    rows = [{"min": n, "max": n, "text": f"result {n}"} for n in range(5, 16)]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={"name": "Shifted", "dice": "2d6+3", "rows": rows},
    )
    assert resp.status_code == 201, resp.text
    table = resp.json()
    for _ in range(40):
        r = client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").json()
        assert 5 <= r["roll"] <= 15
        assert r["index"] is not None


def test_table_rows_must_cover_the_modified_range(client: TestClient) -> None:
    # The bounds shift with the modifier, so 2..12 no longer covers a 2d6+3 table.
    cid = _demo(client)
    rows = [{"min": n, "max": n, "text": f"result {n}"} for n in range(2, 13)]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={"name": "Mismatched", "dice": "2d6+3", "rows": rows},
    )
    assert resp.status_code == 422


def test_select_range_and_weighted() -> None:
    rows = [{"min": 1, "max": 10}, {"min": 11, "max": 18}, {"min": 19, "max": 20}]
    assert tables.select_range(rows, 5) == 0
    assert tables.select_range(rows, 11) == 1
    assert tables.select_range(rows, 20) == 2
    assert tables.select_range([{"min": 1, "max": 5}], 9) is None  # gap → no match

    wrows = [{"weight": 1}, {"weight": 3}]  # cumulative [1, 4] of 4
    assert tables.select_weighted(wrows, 0.0) == 0     # target 0.0 < 1
    assert tables.select_weighted(wrows, 0.20) == 0    # target 0.8 < 1
    assert tables.select_weighted(wrows, 0.30) == 1    # target 1.2 ≥ 1
    assert tables.select_weighted(wrows, 0.99) == 1


# --- API + roll ------------------------------------------------------------
def _fog_table(client: TestClient, cid: str) -> dict:
    body = {
        "name": "Barovia Random Encounters",
        "dice": "1d20",
        "rows": [
            {"min": 1, "max": 10, "text": "No encounter — the mists watch."},
            {"min": 11, "max": 17, "text": "A pack of wolves shadows the party."},
            {"min": 18, "max": 20, "text": "A lone wereraven, watching."},
        ],
    }
    resp = client.post(f"/api/v1/campaigns/{cid}/random-tables", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_roll_range_table(client: TestClient) -> None:
    cid = _demo(client)
    table = _fog_table(client, cid)
    assert table["dice"] == "1d20" and table["row_count"] == 3
    assert any(e["id"] == table["id"] for e in client.get(
        f"/api/v1/campaigns/{cid}/entities?entity_type=random_table").json())

    # Roll many times; every result must be one of the three rows and match its range.
    seen = set()
    for _ in range(40):
        r = client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").json()
        assert 1 <= r["roll"] <= 20
        assert r["index"] in (0, 1, 2)
        seen.add(r["index"])
    assert len(seen) >= 2  # with 40 d20 rolls we should hit multiple bands


def test_row_can_link_to_an_encounter(client: TestClient) -> None:
    cid = _demo(client)
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters", json={"name": "Wolf Ambush", "combatants": []}
    ).json()
    table = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={"name": "T", "dice": "1d1",
              "rows": [{"min": 1, "max": 1, "text": "Wolves!", "target_entity_id": enc["id"]}]},
    ).json()
    # The row resolves its target's name + type for display.
    assert table["rows"][0]["target_name"] == "Wolf Ambush"
    assert table["rows"][0]["target_type"] == "encounter"
    # A d1 always lands on row 0, carrying the link back on the roll.
    r = client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").json()
    assert r["target_entity_id"] == enc["id"] and r["target_type"] == "encounter"


def test_bad_dice_rejected(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/random-tables", json={"name": "X", "dice": "notdice", "rows": []}
    )
    assert resp.status_code == 422


def test_range_rows_must_cover_each_roll_once(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={
            "name": "Broken ranges",
            "dice": "d6",
            "rows": [{"min": 1, "max": 2, "text": "gap"}],
        },
    )
    assert resp.status_code == 422
    assert "cover every possible roll" in resp.json()["detail"]


def test_row_target_must_belong_to_the_campaign(client: TestClient) -> None:
    cid = _demo(client)
    other = client.post("/api/v1/campaigns", json={"name": "Other campaign"}).json()
    foreign_entity = client.post(
        f"/api/v1/campaigns/{other['id']}/entities",
        json={"entity_type": "npc", "name": "Not ours"},
    ).json()
    resp = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={
            "name": "Unsafe target",
            "dice": "d1",
            "rows": [
                {"min": 1, "max": 1, "text": "Nope", "target_entity_id": foreign_entity["id"]}
            ],
        },
    )
    assert resp.status_code == 422
    assert "this campaign" in resp.json()["detail"]


def test_edit_name_dice_and_rows(client: TestClient) -> None:
    cid = _demo(client)
    table = _fog_table(client, cid)
    resp = client.patch(
        f"/api/v1/campaigns/{cid}/random-tables/{table['id']}",
        json={"name": "Svalich Road Encounters", "dice": "d12",
              "rows": [{"min": 1, "max": 12, "text": "Fog and silence."}]},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["name"] == "Svalich Road Encounters"
    assert out["dice"] == "d12" and out["row_count"] == 1
    # The rename propagates to the backing wiki entity.
    ent = client.get(f"/api/v1/campaigns/{cid}/entities/{table['id']}").json()
    assert ent["name"] == "Svalich Road Encounters"


def test_delete_removes_table_and_entity(client: TestClient) -> None:
    cid = _demo(client)
    table = _fog_table(client, cid)
    assert client.delete(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}").status_code == 204

    # Gone from the tables list, the roll endpoint, and the entity graph entirely (hard delete).
    assert all(t["id"] != table["id"] for t in client.get(
        f"/api/v1/campaigns/{cid}/random-tables").json())
    assert client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").status_code == 404
    assert client.get(f"/api/v1/campaigns/{cid}/entities/{table['id']}").status_code == 404


def test_delete_missing_404(client: TestClient) -> None:
    cid = _demo(client)
    assert client.delete(f"/api/v1/campaigns/{cid}/random-tables/nope").status_code == 404


def test_weighted_table_rolls_without_dice(client: TestClient) -> None:
    cid = _demo(client)
    table = client.post(
        f"/api/v1/campaigns/{cid}/random-tables",
        json={"name": "Loot", "dice": "",
              "rows": [{"weight": 1, "text": "Copper"}, {"weight": 5, "text": "Gold"}]},
    ).json()
    r = client.post(f"/api/v1/campaigns/{cid}/random-tables/{table['id']}/roll").json()
    assert r["roll"] is None  # weighted mode has no die
    assert r["index"] in (0, 1) and r["text"] in ("Copper", "Gold")
