"""Sprint 11: party + plugin-driven rests; monster facet filters & variants; perf."""

from __future__ import annotations

import json
import time

from app.core.db import SessionLocal
from app.modules.rules.bestiary import _create_monster
from fastapi.testclient import TestClient

DAY = 24 * 60
_AB = {"str": 10, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10}


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _pc(client: TestClient, cid: str, label: str, max_hp: int) -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": label,
              "doc": {"level": 5, "max_hit_points": max_hp, "armor_class": 16,
                      "abilities": _AB}},
    ).json()["id"]


# --- rests (the exit criterion) --------------------------------------------
def test_long_rest_advances_8h_and_restores_party(client: TestClient) -> None:
    cid = _demo(client)
    pc = _pc(client, cid, "Serah", 44)
    # Join the party wounded (10/44 HP).
    client.post(f"/api/v1/campaigns/{cid}/party/members",
                json={"stat_block_id": pc, "hit_points": 10})

    result = client.post(f"/api/v1/campaigns/{cid}/party/rest", json={"rest_type": "long"}).json()
    assert result["to_time"] - result["from_time"] == 8 * 3600  # 8 hours
    member = result["members"][0]
    assert member["status"]["current_hit_points"] == 44  # restored to max

    # The clock actually moved and a rest event was logged.
    assert client.get(f"/api/v1/campaigns/{cid}/clock").json()["time_game"] == 8 * 3600
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "long_rest_completed" in types and "time_advanced" in types


def test_short_rest_advances_1h(client: TestClient) -> None:
    cid = _demo(client)
    result = client.post(
        f"/api/v1/campaigns/{cid}/party/rest", json={"rest_type": "short"}
    ).json()
    assert result["to_time"] - result["from_time"] == 3600


def test_party_gold_and_membership(client: TestClient) -> None:
    cid = _demo(client)
    pc = _pc(client, cid, "Bthorin", 30)
    client.patch(f"/api/v1/campaigns/{cid}/party", json={"gold": 250})
    party = client.post(f"/api/v1/campaigns/{cid}/party/members",
                        json={"stat_block_id": pc}).json()
    assert party["gold"] == 250
    assert [m["name"] for m in party["members"]] == ["Bthorin"]
    assert party["members"][0]["status"]["current_hit_points"] == 30  # defaulted to max


# --- monster facets & variants ---------------------------------------------
def test_facet_filter_cr_3_6_undead(client: TestClient) -> None:
    cid = _demo(client)
    hits = client.get(
        f"/api/v1/campaigns/{cid}/monsters",
        params={"facet1_num_gte": 3, "facet1_num_lte": 6, "facet1_text": "undead"},
    ).json()
    names = sorted(m["name"] for m in hits)
    assert names == ["Ghost", "Mummy", "Vampire Spawn", "Wight", "Wraith"]


def test_make_variant_copy_on_write(client: TestClient) -> None:
    cid = _demo(client)
    goblin = next(
        m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json() if m["name"] == "Goblin"
    )
    variant = client.post(
        f"/api/v1/campaigns/{cid}/monsters/{goblin['id']}/variant"
    ).json()
    assert variant["variant_of"] == goblin["id"]
    assert variant["source"] == "custom"
    assert variant["name"].endswith("(variant)")


def test_facet_filter_performance(client: TestClient) -> None:
    """NFR-1.2: facet filtering stays well under 100 ms at a few-thousand-monster scale."""
    cid = _demo(client)
    with SessionLocal() as db:
        for i in range(2000):
            cr = float(i % 20)
            mtype = "undead" if i % 3 == 0 else "beast"
            abilities = dict.fromkeys(("str", "dex", "con", "int", "wis", "cha"), 10)
            _create_monster(
                db, cid, "dnd5e", f"Wretch {i}",
                {"size": "Medium", "type": mtype, "armor_class": 12, "hit_points": 20,
                 "challenge_rating": cr, "xp": 100, "abilities": abilities},
                source="custom",
            )
        db.commit()

    start = time.perf_counter()
    hits = client.get(
        f"/api/v1/campaigns/{cid}/monsters",
        params={"facet1_num_gte": 3, "facet1_num_lte": 6, "facet1_text": "undead"},
    ).json()
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(hits) > 5  # the seeded undead + many generated ones
    assert elapsed_ms < 100, f"facet filter took {elapsed_ms:.1f} ms"


def test_simpletest_has_no_rests(client: TestClient) -> None:
    other = client.post(
        "/api/v1/campaigns", json={"name": "Stub", "rule_system_id": "simpletest"}
    ).json()["id"]
    resp = client.post(f"/api/v1/campaigns/{other}/party/rest", json={"rest_type": "long"})
    assert resp.status_code == 422


def test_status_delta_serializes() -> None:
    # Guard: apply_rest returns JSON-serializable status.
    from app.modules.rules import registry

    out = registry.get_system("dnd5e").apply_rest(
        "long", {"current_hit_points": 1}, {"max_hit_points": 30}
    )
    json.dumps(out)
    assert out["current_hit_points"] == 30
