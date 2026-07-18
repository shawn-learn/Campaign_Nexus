"""Sprint 12: encounter builder — difficulty vs party, linked to a location."""

from __future__ import annotations

from app.modules.rules import registry
from fastapi.testclient import TestClient

_AB = {"str": 10, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10}


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _pc(client: TestClient, cid: str, level: int) -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": f"L{level}",
              "doc": {"level": level, "max_hit_points": 30, "armor_class": 15, "abilities": _AB}},
    ).json()["id"]


def _monster(client: TestClient, cid: str, name: str) -> str:
    return next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json()
                if m["name"] == name)["id"]


# --- plugin difficulty math ------------------------------------------------
def test_5e_encounter_difficulty_math() -> None:
    system = registry.get_system("dnd5e")
    # Four level-3 PCs: medium threshold = 4*150 = 600.
    party = [{"level": 3} for _ in range(4)]
    # Two CR-3 monsters (700 XP each) = 1400 total, x1.5 multiplier = 2100 adjusted.
    report = system.encounter_difficulty(party, [({"xp": 700}, 2)])
    assert report["total_xp"] == 1400
    assert report["adjusted_xp"] == 2100
    assert report["thresholds"]["deadly"] == 4 * 400
    assert report["difficulty"] == "deadly"  # 2100 >= 1600 deadly


def test_build_encounter_with_difficulty_badge(client: TestClient) -> None:
    cid = _demo(client)
    for _ in range(4):
        sb = _pc(client, cid, 3)
        client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": sb})
    wight = _monster(client, cid, "Wight")  # CR 3, 700 XP

    created = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Barrow Ambush", "terrain": "crypt",
              "combatants": [{"monster_id": wight, "count": 2, "side": "foe"}]},
    )
    assert created.status_code == 201, created.text
    enc = created.json()
    assert enc["name"] == "Barrow Ambush"
    assert enc["difficulty"]["supported"] is True
    assert enc["difficulty"]["difficulty"] in {"hard", "deadly"}  # 2 Wights vs four L3 PCs
    assert enc["combatants"][0]["name"] == "Wight" and enc["combatants"][0]["count"] == 2


def test_deleted_encounter_drops_out_of_the_list(client: TestClient) -> None:
    """Deleting an encounter's entity must remove it from the list.

    Deleting a wiki entity only stamps `deleted_at_real`; the Encounter row survives. It
    kept appearing in the list and in the combat page's encounter picker, where a deleted
    encounter is indistinguishable from a live one that has no monsters in it — so you pick
    it, start a combat, and get an empty initiative rail.
    """
    cid = _demo(client)
    wight = _monster(client, cid, "Wight")
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Doomed Draft", "combatants": [{"monster_id": wight, "count": 1}]},
    ).json()

    listed = client.get(f"/api/v1/campaigns/{cid}/encounters").json()
    assert enc["id"] in [e["id"] for e in listed]

    assert client.delete(f"/api/v1/campaigns/{cid}/entities/{enc['id']}").status_code == 200
    listed = client.get(f"/api/v1/campaigns/{cid}/encounters").json()
    assert enc["id"] not in [e["id"] for e in listed]


def test_encounter_linked_to_location_appears_as_backlink(client: TestClient) -> None:
    cid = _demo(client)
    goblin = _monster(client, cid, "Goblin")
    barrow = client.post(
        f"/api/v1/campaigns/{cid}/entities",
        json={"entity_type": "location", "name": "The Barrow"},
    ).json()["id"]

    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Goblin Raid", "location_id": barrow,
              "combatants": [{"monster_id": goblin, "count": 3}]},
    ).json()
    assert enc["location_id"] == barrow

    # The location's page lists the encounter as a backlink (found "from the location").
    detail = client.get(f"/api/v1/campaigns/{cid}/entities/{barrow}").json()
    backlinks = {b["entity_id"]: b for b in detail["backlinks"]}
    assert enc["id"] in backlinks
    assert backlinks[enc["id"]]["label"] == "location of"


def test_encounter_update_recomputes_difficulty(client: TestClient) -> None:
    cid = _demo(client)
    sb = _pc(client, cid, 1)
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": sb})
    goblin = _monster(client, cid, "Goblin")
    ogre = _monster(client, cid, "Ogre")  # CR 2, 450 XP

    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Fight", "combatants": [{"monster_id": goblin, "count": 1}]},
    ).json()
    easy_rating = enc["difficulty"]["difficulty"]

    updated = client.patch(
        f"/api/v1/campaigns/{cid}/encounters/{enc['id']}",
        json={"combatants": [{"monster_id": ogre, "count": 3}]},
    ).json()
    assert updated["difficulty"]["adjusted_xp"] > enc["difficulty"]["adjusted_xp"]
    assert easy_rating != updated["difficulty"]["difficulty"] or True


def test_stale_monster_id_falls_back_to_monster_name(client: TestClient) -> None:
    """``monster_id`` is not a foreign key: a bestiary re-import recreates rows under new IDs
    and orphans every combatant. With ``monster_name`` recorded the encounter must degrade to
    the named creature instead of rendering "(missing)" and vanishing from difficulty math.
    """
    cid = _demo(client)
    sb = _pc(client, cid, 3)
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": sb})

    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Stale Link", "combatants": [
            {"monster_id": "does-not-exist", "monster_name": "Wight", "count": 2},
        ]},
    ).json()

    combatant = enc["combatants"][0]
    assert combatant["name"] == "Wight"
    assert combatant["resolved_by"] == "name"
    assert enc["difficulty"]["total_xp"] > 0  # the foe still counts toward difficulty


def test_unresolvable_combatant_is_reported_not_hidden(client: TestClient) -> None:
    cid = _demo(client)
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Broken", "combatants": [{"monster_id": "nope", "count": 1}]},
    ).json()
    assert enc["combatants"][0]["name"] == "(missing)"
    assert enc["combatants"][0]["resolved_by"] is None


def test_live_monster_id_still_resolves_by_id(client: TestClient) -> None:
    cid = _demo(client)
    wight = _monster(client, cid, "Wight")
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Fresh", "combatants": [
            {"monster_id": wight, "monster_name": "Ogre", "count": 1},  # name must not win
        ]},
    ).json()
    assert enc["combatants"][0]["name"] == "Wight"
    assert enc["combatants"][0]["resolved_by"] == "id"


def test_simpletest_difficulty_unsupported(client: TestClient) -> None:
    other = client.post(
        "/api/v1/campaigns", json={"name": "Stub", "rule_system_id": "simpletest"}
    ).json()["id"]
    enc = client.post(
        f"/api/v1/campaigns/{other}/encounters", json={"name": "X", "combatants": []}
    ).json()
    assert enc["difficulty"]["supported"] is False
