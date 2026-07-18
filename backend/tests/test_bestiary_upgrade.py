"""Bestiary upgrade mode: backfill converter improvements without losing GM edits.

``StatBlock`` has no timestamps, so a hand-edited monster is indistinguishable from a freshly
imported one. The merge is therefore additive by construction — these tests pin that down.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_AB = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _doc(**overrides) -> dict:
    doc = {"size": "Medium", "type": "humanoid", "armor_class": 12, "hit_points": 9,
           "challenge_rating": 0.25, "abilities": _AB}
    doc.update(overrides)
    return doc


def _import(client: TestClient, cid: str, name: str, doc: dict, mode: str | None = None) -> dict:
    body: dict = {"monsters": [{"name": name, "rule_system_id": "dnd5e", "doc": doc}]}
    if mode:
        body["mode"] = mode
    return client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json=body).json()


def _fetch(client: TestClient, cid: str, name: str) -> dict:
    return next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters?limit=100000").json()
                if m["name"] == name)


def test_upgrade_adds_new_fields_without_touching_edits(client: TestClient) -> None:
    cid = _demo(client)
    _import(client, cid, "Upgrade Target", _doc(armor_class=12))

    # The GM hand-raised AC; a later converter run also learned to emit speed.
    monster = _fetch(client, cid, "Upgrade Target")
    client.put(f"/api/v1/campaigns/{cid}/stat-blocks/{monster['stat_block_id']}",
               json={"doc": _doc(armor_class=18)})

    result = _import(client, cid, "Upgrade Target",
                     _doc(armor_class=12, speed="40 ft."), mode="upgrade")
    assert result["upgraded"] == 1 and result["imported"] == 0

    doc = _fetch(client, cid, "Upgrade Target")["doc"]
    assert doc["armor_class"] == 18   # the edit survives
    assert doc["speed"] == "40 ft."   # the new field lands


def test_upgrade_backfills_missing_xp(client: TestClient) -> None:
    """Every pre-existing doc has xp absent or 0 — the importer never emitted it."""
    cid = _demo(client)
    _import(client, cid, "No XP", _doc())
    assert "xp" not in _fetch(client, cid, "No XP")["doc"]

    _import(client, cid, "No XP", _doc(xp=50), mode="upgrade")
    assert _fetch(client, cid, "No XP")["doc"]["xp"] == 50


_OLD_ACTIONS = [
    {"name": "Multiattack", "description": "Makes two claw attacks."},
    {"name": "Claw", "kind": "melee", "to_hit": 5, "damage": [{"dice": "1d6+3"}]},
]
_NEW_ACTIONS = [
    {"name": "Claw", "kind": "melee", "to_hit": 5,
     "damage": [{"dice": "1d6+3", "type": "slashing"}, {"dice": "2d6", "type": "fire"}]},
]


def test_upgrade_refreshes_actions_that_lack_damage_types(client: TestClient) -> None:
    """The old converter emitted no damage types and left Multiattack inline; that shape is
    an unambiguous signature, so refreshing it can't clobber a hand-authored list."""
    cid = _demo(client)
    _import(client, cid, "Stale Actions", _doc(actions=_OLD_ACTIONS))

    _import(client, cid, "Stale Actions",
            _doc(actions=_NEW_ACTIONS, multiattack={"description": "Makes two claw attacks."}),
            mode="upgrade")

    doc = _fetch(client, cid, "Stale Actions")["doc"]
    assert [a["name"] for a in doc["actions"]] == ["Claw"]      # Multiattack hoisted out
    assert doc["actions"][0]["damage"][0]["type"] == "slashing"  # types restored
    assert doc["multiattack"]["description"] == "Makes two claw attacks."


def test_upgrade_leaves_typed_actions_alone(client: TestClient) -> None:
    """Once a list has damage types it is either current or hand-edited — don't touch it."""
    cid = _demo(client)
    edited = [{"name": "Claw", "to_hit": 99,
               "damage": [{"dice": "9d6", "type": "radiant"}]}]
    _import(client, cid, "Edited Actions", _doc(actions=edited))

    _import(client, cid, "Edited Actions", _doc(actions=_NEW_ACTIONS), mode="upgrade")

    assert _fetch(client, cid, "Edited Actions")["doc"]["actions"] == edited


def test_upgrade_refuses_custom_and_variant_monsters(client: TestClient) -> None:
    cid = _demo(client)
    goblin = next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json()
                  if m["name"] == "Goblin")
    variant = client.post(f"/api/v1/campaigns/{cid}/monsters/{goblin['id']}/variant").json()

    result = _import(client, cid, variant["name"], _doc(speed="99 ft."), mode="upgrade")
    assert result["skipped"] == 1 and result["upgraded"] == 0
    assert _fetch(client, cid, variant["name"])["doc"].get("speed") != "99 ft."


def test_upgrade_is_idempotent(client: TestClient) -> None:
    cid = _demo(client)
    _import(client, cid, "Stable", _doc())
    _import(client, cid, "Stable", _doc(speed="30 ft."), mode="upgrade")
    again = _import(client, cid, "Stable", _doc(speed="30 ft."), mode="upgrade")
    assert again["upgraded"] == 0 and again["skipped"] == 1


def test_create_mode_is_unchanged_by_default(client: TestClient) -> None:
    cid = _demo(client)
    first = _import(client, cid, "Dup", _doc())
    second = _import(client, cid, "Dup", _doc())
    assert first["imported"] == 1 and second["imported"] == 1  # create still duplicates
