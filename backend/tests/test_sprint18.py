"""Sprint 18 — Nimble, the second-system proof.

Exit criterion: a Nimble campaign runs sheet → encounter → combat → rest end-to-end with
core untouched. Nimble disagrees with 5e about attributes, the HP key, initiative, armor,
monster ratings, rest names and travel, so anything 5e-shaped still hiding in the playbook
fails here rather than in a user's campaign.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_PC = {
    "class_name": "Berserker", "level": 3, "max_hp": 30, "armor": "medium",
    "attributes": {"str": 3, "dex": 1, "int": -1, "wil": 2},
}
_GOBLIN = {"level": 1, "role": "standard", "kind": "humanoid", "size": "small",
           "max_hp": 8, "armor": "light"}


def _campaign(client: TestClient, system: str = "nimble") -> str:
    resp = client.post(
        "/api/v1/campaigns", json={"name": f"{system} game", "rule_system_id": system}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _block(client: TestClient, cid: str, sheet_type: str, label: str, doc: dict) -> str:
    resp = client.post(f"/api/v1/campaigns/{cid}/stat-blocks", json={
        "rule_system_id": "nimble", "sheet_type": sheet_type, "label": label, "doc": doc,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------------------------------------------------------------------------- #
# The plugin itself
# --------------------------------------------------------------------------- #
def test_nimble_is_installed_and_ships_no_content(client: TestClient) -> None:
    systems = {s["id"]: s for s in client.get("/api/v1/rule-systems").json()}
    assert "nimble" in systems
    assert set(systems["nimble"]["sheet_types"]) == {"pc", "npc", "monster"}
    # Licensing: the approximation ships schemas, not rules text or monsters.
    from app.modules.rules import registry

    assert registry.get_system("nimble").content_packs() == []


def test_four_attributes_not_six_and_they_are_modifiers(client: TestClient) -> None:
    schema = client.get("/api/v1/rule-systems/nimble/schema/pc").json()
    assert set(schema["properties"]["attributes"]["properties"]) == {"str", "dex", "int", "wil"}

    result = client.post("/api/v1/rule-systems/nimble/validate",
                         json={"sheet_type": "pc", "doc": _PC}).json()
    assert result["valid"], result["errors"]
    # No score-to-modifier arithmetic: a +3 is a +3 (5e would derive +3 from a score of 16).
    assert result["derived"]["attribute_modifiers"]["str"] == 3
    assert result["derived"]["armor_value"] == 2  # medium armor turns aside 2

    # A 5e ability score would be out of range, and cha does not exist here.
    bad = client.post("/api/v1/rule-systems/nimble/validate",
                      json={"sheet_type": "pc", "doc": {**_PC, "attributes": {"cha": 16}}}).json()
    assert not bad["valid"]


def test_monsters_are_rated_by_level_and_role_not_cr(client: TestClient) -> None:
    manifest = client.get("/api/v1/rule-systems/nimble/facets").json()
    assert [f["label"] for f in manifest] == ["Level", "Kind", "Role"]


# --------------------------------------------------------------------------- #
# sheet -> party -> encounter -> combat -> rest
# --------------------------------------------------------------------------- #
def test_a_nimble_campaign_runs_end_to_end(client: TestClient) -> None:
    cid = _campaign(client)

    # 1. Sheet. The party joins; HP comes from `max_hp`, a key 5e has never heard of.
    pc = _block(client, cid, "pc", "Ragna", _PC)
    party = client.post(f"/api/v1/campaigns/{cid}/party/members",
                        json={"stat_block_id": pc}).json()
    member = party["members"][0]
    assert (member["hp"], member["max_hp"]) == (30, 30)
    assert member["status"]["hp"] == 30          # plugin-shaped status...
    assert "current_hit_points" not in member["status"]  # ...not 5e's
    assert party["rest_types"] == ["field", "safe"]

    # 2. Encounter, with difficulty priced by level+role rather than CR/XP. Nimble ships no
    # content pack, so the bestiary is stocked by import — and validated against its schema.
    report = client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json={
        "monsters": [{"name": "Goblin", "doc": _GOBLIN}],
    }).json()
    assert report == {"imported": 1, "errors": []}
    monster = client.get(f"/api/v1/campaigns/{cid}/monsters").json()[0]
    assert monster["facets"]["facet1_num"] == 1  # level, where 5e would have put CR

    encounter = client.post(f"/api/v1/campaigns/{cid}/encounters", json={
        "name": "Goblin ambush", "combatants": [{"monster_id": monster["id"], "count": 4}],
    }).json()
    assert encounter["difficulty"]["supported"] is True
    # 4 standard level-1 goblins = weight 4 vs a level-3 budget → over 1.15x -> hard.
    assert encounter["difficulty"]["difficulty"] == "hard"

    # 3. Combat. Nimble rolls no initiative, so the party acts before the monsters.
    run = client.post(f"/api/v1/campaigns/{cid}/combats",
                      json={"encounter_id": encounter["id"]}).json()
    state = run["state"]
    order = [state["combatants"][i]["name"] for i in state["order"]]
    assert order[0] == "Ragna"
    assert all(name.startswith("Goblin") for name in order[1:])
    assert state["combatants"][state["order"][1]]["max_hp"] == 8  # from the monster's max_hp

    # Hit a goblin, then end the fight. (The four goblins tie on initiative, so which one
    # sorts first is arbitrary — take whoever is next in the order.)
    goblin_id = state["order"][1]
    goblin_name = state["combatants"][goblin_id]["name"]
    client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/actions",
                json={"action_type": "damage", "payload": {"id": goblin_id, "amount": 8}})
    summary = client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/end").json()
    assert summary["defeated"] == [goblin_name]

    # 4. Rest. "safe", not "long" — and it restores HP through the plugin's own key.
    rested = client.post(f"/api/v1/campaigns/{cid}/party/rest", json={"rest_type": "safe"}).json()
    assert rested["members"][0]["hp"] == 30

    bad = client.post(f"/api/v1/campaigns/{cid}/party/rest", json={"rest_type": "long"})
    assert bad.status_code == 422
    assert "no 'long' rest" in bad.json()["detail"]

    # The timeline narrates a rest whose name the chronicle has never seen.
    titles = [t["title"] for t in client.get(f"/api/v1/campaigns/{cid}/timeline").json()]
    assert "The party completed a safe rest." in titles


def test_rolling_initiative_does_nothing_in_a_system_that_has_none(client: TestClient) -> None:
    """Nimble rolls no initiative: the party acts, then the monsters do.

    So "roll initiative for everyone" must leave that ranking exactly as the plugin set it,
    rather than shuffle it with a d20 the system does not have. This is the check that keeps
    the tracker's initiative feature from being a quietly 5e-only one.
    """
    cid = _campaign(client)
    pc = _block(client, cid, "pc", "Ragna", _PC)
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": pc})
    client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json={
        "monsters": [{"name": "Goblin", "doc": _GOBLIN}],
    })
    monster = client.get(f"/api/v1/campaigns/{cid}/monsters").json()[0]
    encounter = client.post(f"/api/v1/campaigns/{cid}/encounters", json={
        "name": "Ambush", "combatants": [{"monster_id": monster["id"], "count": 2}],
    }).json()

    run = client.post(f"/api/v1/campaigns/{cid}/combats",
                      json={"encounter_id": encounter["id"]}).json()
    before = [run["state"]["combatants"][i]["initiative"] for i in run["state"]["order"]]

    out = client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/initiative",
                      json={"scope": "all"}).json()
    after = [out["state"]["combatants"][i]["initiative"] for i in out["state"]["order"]]

    assert after == before == [1, 0, 0]  # the party's 1 still outranks the monsters' 0
    # And no dice were thrown, because there is no die to throw.
    assert client.get(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/rolls").json() == []


def test_partial_hp_survives_into_combat(client: TestClient) -> None:
    """The combat tracker reads live HP through the plugin, not through `current_hit_points`."""
    cid = _campaign(client)
    pc = _block(client, cid, "pc", "Ragna", _PC)
    client.post(f"/api/v1/campaigns/{cid}/party/members",
                json={"stat_block_id": pc, "hit_points": 11})

    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={}).json()
    combatant = next(iter(run["state"]["combatants"].values()))
    assert (combatant["hp"], combatant["max_hp"]) == (11, 30)


def test_nimble_has_no_travel_rules_so_the_planner_degrades(client: TestClient) -> None:
    cid = _campaign(client)
    resp = client.post(f"/api/v1/campaigns/{cid}/party/travel/preview",
                       json={"legs": [{"distance": 10}]})
    assert resp.status_code == 501
    assert "no travel rules" in resp.json()["detail"]


def test_a_nimble_journey_would_still_rest_if_it_could(client: TestClient) -> None:
    """`overnight_rest_type` is the seam: 5e says 'long', Nimble says 'safe'."""
    from app.modules.rules import registry

    assert registry.get_system("dnd5e").overnight_rest_type() == "long"
    assert registry.get_system("nimble").overnight_rest_type() == "safe"
    assert registry.get_system("simpletest").overnight_rest_type() is None


# --------------------------------------------------------------------------- #
# The 5e campaign must be untouched by all of this
# --------------------------------------------------------------------------- #
def test_dnd5e_still_behaves(client: TestClient) -> None:
    cid = client.get("/api/v1/campaigns").json()[0]["id"]
    _AB = {"str": 10, "dex": 14, "con": 12, "int": 10, "wis": 10, "cha": 10}
    block = client.post(f"/api/v1/campaigns/{cid}/stat-blocks", json={
        "rule_system_id": "dnd5e", "sheet_type": "pc", "label": "Serah",
        "doc": {"level": 5, "max_hit_points": 44, "armor_class": 16, "abilities": _AB},
    }).json()["id"]

    party = client.post(f"/api/v1/campaigns/{cid}/party/members",
                        json={"stat_block_id": block, "hit_points": 10}).json()
    member = party["members"][0]
    assert (member["hp"], member["max_hp"]) == (10, 44)
    assert member["status"]["current_hit_points"] == 10  # 5e keeps its own vocabulary
    assert party["rest_types"] == ["short", "long"]

    rested = client.post(f"/api/v1/campaigns/{cid}/party/rest",
                         json={"rest_type": "long"}).json()
    assert rested["members"][0]["hp"] == 44

    # Initiative still comes from DEX (+2), unlike Nimble's flat party-first ordering.
    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={}).json()
    combatant = next(iter(run["state"]["combatants"].values()))
    assert combatant["initiative"] == 2
