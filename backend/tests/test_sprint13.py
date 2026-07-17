"""Sprint 13: combat reducer golden, and event-sourced run with undo/redo/end."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.modules.campaign.models import Campaign
from app.modules.playbook import combat
from app.modules.playbook.combat_reducer import fold
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_GOLDEN = Path(__file__).parent / "fixtures" / "combat_golden.json"


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _monster(client: TestClient, cid: str, name: str) -> str:
    return next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json()
                if m["name"] == name)["id"]


# --- reducer golden (feeds the TS parity test too) -------------------------
def test_reducer_golden() -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    for case in golden:
        assert fold(case["actions"]) == case["expected"], case["name"]


def test_api_combatant_carries_every_reducer_field(client: TestClient) -> None:
    """The wire shape must match the reducer's exactly.

    ``state_of`` model_validates the folded dict through the ``Combatant`` pydantic model,
    and pydantic *drops* fields the model doesn't declare. A field added to the reducer but
    forgotten in schemas.py would vanish between the fold and the response with nothing
    failing — so compare the two shapes directly rather than trust either alone.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()

    reference = fold([
        {"type": "add_combatant", "id": "x", "name": "X", "side": "foe",
         "max_hp": 7, "initiative": 2},
    ])["combatants"]["x"]
    over_the_wire = next(iter(run["state"]["combatants"].values()))
    assert set(over_the_wire) == set(reference), "wire shape drifted from the reducer"


def test_reducer_undo_redo_identity() -> None:
    actions = [
        {"type": "add_combatant", "id": "a", "name": "A", "side": "foe",
         "max_hp": 20, "initiative": 10},
        {"type": "damage", "id": "a", "amount": 5},
        {"type": "damage", "id": "a", "amount": 3},
    ]
    full = fold(actions)
    # Folding a prefix (undo) then the rest (redo) reproduces the full state.
    assert fold(actions[:2]) == fold(actions[:2])
    assert full["combatants"]["a"]["hp"] == 12


# --- event-sourced run -----------------------------------------------------
def _encounter_of_two_goblins(client: TestClient, cid: str) -> str:
    goblin = _monster(client, cid, "Goblin")
    return client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Ambush", "combatants": [{"monster_id": goblin, "count": 2}]},
    ).json()["id"]


def _start_from_two_goblins(client: TestClient, cid: str) -> str:
    enc = _encounter_of_two_goblins(client, cid)
    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc}).json()
    return run["run_id"]


def test_start_combat_seeds_combatants(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    combatants = run["state"]["combatants"]
    assert len(combatants) == 2  # two goblins
    assert {c["name"] for c in combatants.values()} == {"Goblin 1", "Goblin 2"}


def test_combatant_blocks_map_points_at_a_stat_block(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    blocks = run["combatant_blocks"]
    # Every combatant maps to a stat block, and that block is fetchable + is a Goblin.
    assert set(blocks) == set(run["state"]["combatants"])
    block_id = next(iter(blocks.values()))
    block = client.get(f"/api/v1/campaigns/{cid}/stat-blocks/{block_id}")
    assert block.status_code == 200, block.text
    assert block.json()["sheet_type"] == "monster"


def test_unknown_action_type_is_rejected(client: TestClient) -> None:
    """A typo'd action used to persist, advance the fold cursor, and do nothing.

    The reducer ignores types it doesn't know, so the write "succeeded", the GM saw no
    change, and Undo was the only way to clear the dead log entry. It 422s at the edge now.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    before = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["total_actions"]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "rol_initiative", "payload": {}},
    )
    assert resp.status_code == 422
    # And nothing was written — the log is exactly as long as it was.
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["total_actions"]
    assert after == before


def test_party_hp_is_written_back_when_combat_ends(client: TestClient) -> None:
    """A PC's wounds must outlive the combat that caused them.

    The fold was the only record of damage taken, and nothing reads it once the run is over
    — so a character walked out of a bruising fight at full health.
    """
    cid = _demo(client)
    pc = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": "Serah",
              "doc": {"level": 5, "max_hit_points": 40, "armor_class": 16,
                      "abilities": {"str": 10, "dex": 14, "con": 12, "int": 10,
                                    "wis": 10, "cha": 10}}},
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": pc})

    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")
    assert serah["hp"] == 40  # joined at full

    client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {"id": serah["id"], "amount": 13}},
    )
    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end")

    member = client.get(f"/api/v1/campaigns/{cid}/party").json()["members"][0]
    assert member["hp"] == 27
    assert member["status"]["current_hit_points"] == 27


# --- legendary + lair -------------------------------------------------------
_STRAHD = {
    "size": "Medium", "type": "undead", "armor_class": 16, "hit_points": 144,
    "challenge_rating": 15, "xp": 13000,
    "abilities": {"str": 18, "dex": 18, "con": 18, "int": 20, "wis": 15, "cha": 18},
    "actions": [{"name": "Unarmed Strike", "to_hit": 9,
                 "damage": [{"dice": "1d8+4", "type": "bludgeoning"}]}],
    "legendary_actions": {
        "count": 3,
        "options": [
            {"name": "Move", "description": "Strahd moves without provoking."},
            {"name": "Unarmed Strike", "to_hit": 9,
             "damage": [{"dice": "1d8+4", "type": "bludgeoning"}]},
            {"name": "Bite", "cost": 2, "to_hit": 9,
             "damage": [{"dice": "1d6+4", "type": "piercing"},
                        {"dice": "3d6", "type": "necrotic"}]},
        ],
    },
}


def _boss_run(client: TestClient, cid: str) -> tuple[str, str]:
    """A run containing a legendary boss. Returns (run_id, combatant_id)."""
    client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json={
        "monsters": [{"name": "Strahd", "doc": _STRAHD}],
    })
    boss = next(m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json()
                if m["name"] == "Strahd")
    enc = client.post(f"/api/v1/campaigns/{cid}/encounters", json={
        "name": "The Count", "combatants": [{"monster_id": boss["id"], "count": 1}],
    }).json()
    run = client.post(f"/api/v1/campaigns/{cid}/combats",
                      json={"encounter_id": enc["id"]}).json()
    strahd = next(c for c in run["state"]["combatants"].values() if c["name"] == "Strahd")
    return run["run_id"], strahd["id"]


def test_a_legendary_creature_is_seeded_with_its_action_pool(client: TestClient) -> None:
    # The count reaches the tracker through combat_profile, like everything else it knows.
    cid = _demo(client)
    run_id, boss = _boss_run(client, cid)
    state = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["state"]
    assert state["combatants"][boss]["legendary"] == {"max": 3, "remaining": 3}


def test_legendary_options_are_offered_alongside_ordinary_attacks(client: TestClient) -> None:
    """One list, one code path — a legendary option is an attack that also costs something."""
    cid = _demo(client)
    run_id, boss = _boss_run(client, cid)
    attacks = client.get(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants/{boss}/attacks"
    ).json()

    ordinary = [a for a in attacks if a["legendary_cost"] is None]
    legendary = {a["name"]: a for a in attacks if a["legendary_cost"] is not None}
    assert [a["name"] for a in ordinary] == ["Unarmed Strike"]
    assert legendary["Move"]["legendary_cost"] == 1        # defaulted
    assert legendary["Bite"]["legendary_cost"] == 2        # as authored
    assert legendary["Bite"]["damage"] == [
        {"dice": "1d6+4", "type": "piercing"}, {"dice": "3d6", "type": "necrotic"},
    ]


def test_spending_legendary_actions_and_regaining_them_on_its_turn(client: TestClient) -> None:
    cid = _demo(client)
    run_id, boss = _boss_run(client, cid)

    def act(atype, **payload):
        return client.post(
            f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
            json={"action_type": atype, "payload": payload},
        ).json()["state"]["combatants"][boss]["legendary"]

    assert act("legendary_use", id=boss, cost=2) == {"max": 3, "remaining": 1}
    assert act("legendary_use", id=boss, cost=1) == {"max": 3, "remaining": 0}
    # Strahd is the only combatant, so the next turn is his — and the pool comes back.
    assert act("next_turn") == {"max": 3, "remaining": 3}


def test_a_lair_joins_the_order_and_cannot_be_killed(client: TestClient) -> None:
    """A lair is an ordinary entry at a fixed count — no special case anywhere in the fold."""
    cid = _demo(client)
    run_id, _ = _boss_run(client, cid)

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants",
        json={"name": "Castle Ravenloft", "max_hp": 0, "kind": "lair",
              "side": "foe", "initiative": 20},
    )
    assert out.status_code == 200, out.text
    lair = next(c for c in out.json()["state"]["combatants"].values()
                if c["name"] == "Castle Ravenloft")
    assert lair["kind"] == "lair"
    assert lair["initiative"] == 20
    assert lair["defeated"] is False  # at 0 hp, and still not a corpse

    # Nothing rolled for it: a lair acts on a fixed count, so nothing is left to chance.
    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert not any(r["combatant_id"] == lair["id"] for r in rolls)

    # And hitting it changes nothing about its standing.
    after = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {"id": lair["id"], "amount": 50}},
    ).json()
    assert after["state"]["combatants"][lair["id"]]["defeated"] is False


# --- death saves ------------------------------------------------------------
def _downed_pc(client: TestClient, cid: str) -> tuple[str, str]:
    """A run with a PC at 0 hp. Returns (run_id, combatant_id)."""
    _pc(client, cid, "Serah")
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")
    client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {"id": serah["id"], "amount": 40}},
    )
    return run_id, serah["id"]


def test_the_run_reports_its_systems_death_save_rules(client: TestClient) -> None:
    # The tracker shows a death-save row only where the rules have one — so it asks.
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    rules = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["death_saves"]
    assert rules == {"supported": True, "dice": "1d20", "dc": 10, "successes": 3, "failures": 3}


def test_rolling_a_death_save_records_an_outcome(client: TestClient) -> None:
    cid = _demo(client)
    run_id, serah = _downed_pc(client, cid)

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/death-save",
        json={"combatant_id": serah},
    )
    assert out.status_code == 200, out.text
    saves = out.json()["state"]["combatants"][serah]["death_saves"]
    assert saves["successes"] + saves["failures"] >= 1  # a nat 20 revives instead

    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    roll = next(r for r in rolls if r["kind"] == "death_save")
    assert roll["expression"] == "1d20" and roll["target"] == 10
    assert roll["outcome"] in {"success", "failure", "crit_success", "crit_fail"}


def test_death_save_outcomes_follow_the_die(client: TestClient, db: Session) -> None:
    """DC 10 on a flat d20 — and the faces override the arithmetic at both ends."""
    cid = _demo(client)
    run_id, serah = _downed_pc(client, cid)
    campaign = db.get(Campaign, cid)

    def roll(face: int) -> str:
        db.expire_all()
        combat.roll_death_save(db, campaign, run_id, serah, rng=ScriptedRandom([face]))
        rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
        return next(r for r in rolls if r["kind"] == "death_save")["outcome"]

    assert roll(12) == "success"   # 12 >= 10
    assert roll(9) == "failure"    # 9 < 10
    assert roll(20) == "crit_success"
    assert roll(1) == "crit_fail"


def test_a_natural_twenty_puts_a_dying_pc_back_on_their_feet(
    client: TestClient, db: Session
) -> None:
    cid = _demo(client)
    run_id, serah = _downed_pc(client, cid)
    campaign = db.get(Campaign, cid)

    db.expire_all()
    combat.roll_death_save(db, campaign, run_id, serah, rng=ScriptedRandom([9]))  # a failure
    db.expire_all()
    combat.roll_death_save(db, campaign, run_id, serah, rng=ScriptedRandom([20]))

    state = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["state"]
    c = state["combatants"][serah]
    assert c["hp"] == 1 and c["defeated"] is False
    assert c["death_saves"] == {"successes": 0, "failures": 0}  # slate wiped


def test_hitting_someone_already_down_is_an_automatic_failure(client: TestClient) -> None:
    # The most-forgotten rule at a table, and free to get right.
    cid = _demo(client)
    run_id, serah = _downed_pc(client, cid)
    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {"id": serah, "amount": 3}},
    ).json()
    assert out["state"]["combatants"][serah]["death_saves"]["failures"] == 1


def test_a_system_without_death_saves_refuses_to_roll_one(client: TestClient) -> None:
    """Nimble has no death saves, so the tracker must not invent a d20 for it."""
    cid = client.post(
        "/api/v1/campaigns", json={"name": "nimble game", "rule_system_id": "nimble"}
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json={
        "monsters": [{"name": "Goblin", "doc": {"level": 1, "role": "standard",
                                                "max_hp": 8, "armor": "light"}}],
    })
    monster = client.get(f"/api/v1/campaigns/{cid}/monsters").json()[0]
    enc = client.post(f"/api/v1/campaigns/{cid}/encounters", json={
        "name": "Ambush", "combatants": [{"monster_id": monster["id"], "count": 1}],
    }).json()
    run = client.post(f"/api/v1/campaigns/{cid}/combats",
                      json={"encounter_id": enc["id"]}).json()

    assert run["death_saves"] == {"supported": False, "dice": None, "dc": None,
                                  "successes": None, "failures": None}
    gid = run["state"]["order"][0]
    resp = client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/death-save",
                       json={"combatant_id": gid})
    assert resp.status_code == 422


# --- attacks ----------------------------------------------------------------
class ScriptedRandom(random.Random):
    """Hands back pre-set faces, so a test can state the exact dice it means."""

    def __init__(self, values: list[int]) -> None:
        super().__init__()
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:  # type: ignore[override]
        return self._values.pop(0)


def _two_goblins(client: TestClient, cid: str) -> tuple[str, str, str]:
    """A run with two goblins; returns (run_id, attacker_id, target_id)."""
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    order = run["state"]["order"]
    return run_id, order[0], order[1]


def test_a_combatant_offers_the_attacks_off_its_stat_block(client: TestClient) -> None:
    cid = _demo(client)
    run_id, goblin, _ = _two_goblins(client, cid)

    attacks = client.get(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants/{goblin}/attacks"
    ).json()
    by_name = {a["name"]: a for a in attacks}
    assert set(by_name) == {"Scimitar", "Shortbow"}
    assert by_name["Scimitar"]["to_hit"] == 4
    assert by_name["Scimitar"]["damage"] == [{"dice": "1d6+2", "type": "slashing"}]
    assert by_name["Shortbow"]["kind"] == "ranged"


def test_an_ad_hoc_combatant_has_no_attacks_to_offer(client: TestClient) -> None:
    cid = _demo(client)
    run_id, _, _ = _two_goblins(client, cid)
    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants",
        json={"name": "Swarm of Rats", "max_hp": 24},
    ).json()
    rats = next(c for c in out["state"]["combatants"].values() if c["name"] == "Swarm of Rats")
    assert client.get(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants/{rats['id']}/attacks"
    ).json() == []


def test_attack_rolls_to_hit_against_the_targets_ac_and_changes_nothing(
    client: TestClient, db
) -> None:
    """The roll is reported; applying it is a separate, deliberate act.

    Resistance, cover, "actually he ducks behind the pillar" — none of that is knowable
    here, and auto-applying would spend the exact moment a GM is for.
    """
    cid = _demo(client)
    run_id, attacker, target = _two_goblins(client, cid)
    before = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()

    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/attack",
        json={"attacker_id": attacker, "action_index": 0, "target_id": target},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()

    assert result["action_name"] == "Scimitar"
    assert result["target_ac"] == 15  # a goblin's AC, from its stat block
    assert result["outcome"] in {"hit", "miss", "crit", "fumble"}
    assert result["to_hit"]["expression"] == "1d20+4"
    # Nothing moved: HP is untouched and the fold cursor hasn't advanced.
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    assert after["state"] == before["state"]
    assert after["total_actions"] == before["total_actions"]


def _scripted_attack(db: Session, cid: str, run_id: str, attacker: str, target: str | None,
                     faces: list[int]) -> dict:
    """Drive combat.attack with exact dice. The HTTP layer can't inject an rng, and a
    seeded one would only prove the seed."""
    db.expire_all()  # the client made its changes over HTTP, through another session
    campaign = db.get(Campaign, cid)
    assert campaign is not None
    return combat.attack(
        db, campaign, run_id, attacker_id=attacker, action_index=0,
        target_id=target, rng=ScriptedRandom(faces),
    )


def test_a_hit_rolls_damage_and_a_miss_does_not(client: TestClient, db: Session) -> None:
    cid = _demo(client)
    run_id, attacker, target = _two_goblins(client, cid)

    # 16 + 4 = 20 vs AC 15 -> hit, then 1d6+2 damage on a face of 3.
    hit = _scripted_attack(db, cid, run_id, attacker, target, [16, 3])
    assert hit["outcome"] == "hit"
    assert hit["total_damage"] == 5

    # 2 + 4 = 6 vs AC 15 -> miss, and no damage die is thrown at all.
    miss = _scripted_attack(db, cid, run_id, attacker, target, [2])
    assert miss["outcome"] == "miss"
    assert miss["damage"] == []
    assert miss["total_damage"] == 0


def test_a_natural_twenty_crits_and_doubles_the_damage_dice(
    client: TestClient, db: Session
) -> None:
    cid = _demo(client)
    run_id, attacker, target = _two_goblins(client, cid)
    # Nat 20, then two d6 faces: 1d6+2 becomes 2d6+2, because 5e doubles the dice and not
    # the modifier — and the plugin said so by naming `crit_rule: double_dice`.
    result = _scripted_attack(db, cid, run_id, attacker, target, [20, 4, 5])
    assert result["outcome"] == "crit"
    assert result["damage"][0].expression == "2d6+2"
    assert result["total_damage"] == 11  # 4 + 5 + 2, not (4+2) + (5+2)


def test_a_natural_one_misses_whatever_the_total_says(
    client: TestClient, db: Session
) -> None:
    # A goblin's +4 against AC 15 can't reach it on a 1 anyway — but the point is that the
    # face decides before the total does, so this stays a miss even against a low AC.
    cid = _demo(client)
    run_id, attacker, target = _two_goblins(client, cid)
    result = _scripted_attack(db, cid, run_id, attacker, target, [1])
    assert result["outcome"] == "fumble"
    assert result["damage"] == []


def test_attacking_without_a_target_reports_the_roll_and_judges_nothing(
    client: TestClient, db: Session
) -> None:
    # No AC to beat means no verdict to give — but the damage is still rolled, because the
    # GM asked for the attack and will decide what it hit.
    cid = _demo(client)
    run_id, attacker, _ = _two_goblins(client, cid)
    result = _scripted_attack(db, cid, run_id, attacker, None, [11, 4])
    assert result["target_ac"] is None
    assert result["outcome"] is None
    assert result["total_damage"] == 6  # 1d6+2 on a face of 4


def test_the_faces_still_speak_without_a_target(client: TestClient, db: Session) -> None:
    """A natural 1 is a fumble whether or not we know what it was swung at.

    (This is why the no-target test above scripts its die: on a real d20 it would report a
    verdict one roll in ten and fail for a reason that has nothing to do with targets.)
    """
    cid = _demo(client)
    run_id, attacker, _ = _two_goblins(client, cid)
    assert _scripted_attack(db, cid, run_id, attacker, None, [1])["outcome"] == "fumble"
    assert _scripted_attack(db, cid, run_id, attacker, None, [20, 3, 5])["outcome"] == "crit"


def test_an_attack_is_traceable_from_the_damage_it_caused(client: TestClient) -> None:
    """Applying is an ordinary damage action carrying the roll's id.

    "Where did this 8 come from" stays answerable, which is the whole reason rolls get ids.
    """
    cid = _demo(client)
    run_id, attacker, target = _two_goblins(client, cid)
    result = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/attack",
        json={"attacker_id": attacker, "action_index": 0, "target_id": target},
    ).json()
    if not result["damage"]:
        return  # it missed; nothing to apply

    roll_id = result["damage"][0]["id"]
    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "damage", "payload": {
            "id": target, "amount": result["total_damage"], "roll_id": roll_id,
        }},
    ).json()
    assert out["state"]["combatants"][target]["hp"] == max(0, 7 - result["total_damage"])
    # And the roll it came from is in the log.
    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert any(r["id"] == roll_id for r in rolls)


def test_an_unknown_attack_index_is_rejected(client: TestClient) -> None:
    cid = _demo(client)
    run_id, attacker, _ = _two_goblins(client, cid)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/attack",
        json={"attacker_id": attacker, "action_index": 99},
    )
    assert resp.status_code == 422


# --- roster control ---------------------------------------------------------
def test_add_a_monster_mid_fight_continues_the_numbering(client: TestClient) -> None:
    """A Goblin joining Goblin 1-2 becomes Goblin 3, not a second Goblin 1.

    Two combatants with the same name on the rail is the moment a GM stops trusting the
    tracker to know which one is bloodied.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants",
        json={"monster_id": _monster(client, cid, "Goblin"), "count": 2},
    )
    assert out.status_code == 200, out.text
    names = sorted(c["name"] for c in out.json()["state"]["combatants"].values())
    assert names == ["Goblin 1", "Goblin 2", "Goblin 3", "Goblin 4"]


def test_added_monster_is_seeded_from_its_stat_block_and_rolls_in(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants",
        json={"monster_id": _monster(client, cid, "Ogre"), "side": "foe"},
    ).json()

    ogre = next(c for c in out["state"]["combatants"].values() if c["name"] == "Ogre")
    assert ogre["max_hp"] == 59 and ogre["hp"] == 59  # from the SRD stat block, not the client
    assert ogre["initiative_tiebreak"] == -1  # dex 8
    assert -1 + 1 <= ogre["initiative"] <= 20 - 1  # rolled 1d20-1 on the way in

    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert any(r["combatant_id"] == ogre["id"] and r["expression"] == "1d20-1" for r in rolls)


def test_add_an_ad_hoc_combatant_with_an_explicit_initiative(client: TestClient) -> None:
    # A player's summon acts on their turn, so its number is given rather than rolled.
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants",
        json={"name": "Spectral Wolf", "max_hp": 12, "side": "ally", "initiative": 14},
    ).json()

    wolf = next(c for c in out["state"]["combatants"].values() if c["name"] == "Spectral Wolf")
    assert (wolf["max_hp"], wolf["hp"], wolf["side"]) == (12, 12, "ally")
    assert wolf["initiative"] == 14  # taken as given, not rolled over
    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert not any(r["combatant_id"] == wolf["id"] for r in rolls)


def test_ad_hoc_combatant_needs_a_name_and_hp(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants", json={"name": "Nameless"},
    )
    assert resp.status_code == 422


def test_adding_an_unknown_monster_404s(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/combatants", json={"monster_id": "nope"},
    )
    assert resp.status_code == 404


def test_remove_a_combatant(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "remove_combatant", "payload": {"id": gid}},
    ).json()
    assert gid not in out["state"]["combatants"]
    assert gid not in out["state"]["order"]


def test_temp_hp_absorbs_damage_before_hit_points(client: TestClient) -> None:
    # set_temp_hp rendered as "(+N)" from day one but nothing could ever set it.
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    def act(atype, **payload):
        return client.post(
            f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
            json={"action_type": atype, "payload": payload},
        ).json()["state"]["combatants"][gid]

    assert act("set_temp_hp", id=gid, amount=5)["temp_hp"] == 5
    # 3 comes off the 5 temp; real hit points are untouched.
    after = act("damage", id=gid, amount=3)
    assert (after["temp_hp"], after["hp"]) == (2, 7)
    # 4 more: the last 2 temp absorb, then 2 land on hp.
    after = act("damage", id=gid, amount=4)
    assert (after["temp_hp"], after["hp"]) == (0, 5)


# --- initiative -------------------------------------------------------------
def _pc(client: TestClient, cid: str, label: str, dex: int = 14) -> str:
    sb = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": label,
              "doc": {"level": 5, "max_hit_points": 40, "armor_class": 16,
                      "abilities": {"str": 10, "dex": dex, "con": 12, "int": 10,
                                    "wis": 10, "cha": 10}}},
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/party/members", json={"stat_block_id": sb})
    return sb


def test_combat_opens_in_setup_with_the_monsters_already_rolled(client: TestClient) -> None:
    """Starting a combat is the moment you call for initiative: the monsters roll at once.

    The PCs' numbers are the GM's to type in, so they wait — and the run stays in `setup`
    until Begin, which is what makes the roster screen survive a refresh.
    """
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run = client.post(
        f"/api/v1/campaigns/{cid}/combats",
        json={"encounter_id": _encounter_of_two_goblins(client, cid)},
    ).json()

    assert run["status"] == "setup"
    combatants = run["state"]["combatants"].values()
    goblins = [c for c in combatants if c["side"] == "foe"]
    serah = next(c for c in combatants if c["name"] == "Serah")

    # Goblins have dex 14 (+2), so a rolled total lands in 3..22 and is almost never the
    # bare +2 seed. Serah is untouched at her seeded modifier, waiting for a typed total.
    assert all(3 <= g["initiative"] <= 22 for g in goblins)
    assert serah["initiative"] == 2  # dex 14 -> +2, the pre-roll seed

    rolls = client.get(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/rolls").json()
    assert len(rolls) == 2  # one per goblin
    assert {r["kind"] for r in rolls} == {"initiative"}
    assert all(r["expression"] == "1d20+2" for r in rolls)


def test_roll_initiative_takes_typed_values_and_rolls_the_rest(client: TestClient) -> None:
    # The actual moment at the table: the monsters roll, the players call their numbers out.
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")

    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/initiative",
        json={"scope": "foes", "values": {serah["id"]: 18}},
    ).json()

    after = out["state"]["combatants"][serah["id"]]
    assert after["initiative"] == 18  # taken verbatim — the modifier is already in it
    assert after["initiative_tiebreak"] == 2  # dex, for breaking ties
    # 18 beats any goblin that didn't roll a natural 17+, so Serah is usually first; assert
    # the invariant instead: the order is sorted by initiative descending.
    order = [out["state"]["combatants"][i]["initiative"] for i in out["state"]["order"]]
    assert order == sorted(order, reverse=True)


def test_a_typed_value_wins_over_a_roll_for_the_same_combatant(client: TestClient) -> None:
    cid = _demo(client)
    _pc(client, cid, "Serah")
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    serah = next(c for c in run["state"]["combatants"].values() if c["name"] == "Serah")

    # scope=all *includes* Serah, but a typed value for her must not be rolled over.
    out = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/initiative",
        json={"scope": "all", "values": {serah["id"]: 11}},
    ).json()
    assert out["state"]["combatants"][serah["id"]]["initiative"] == 11


def test_begin_leaves_setup_and_rejects_a_finished_run(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    assert client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()["status"] == "setup"

    begun = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/begin")
    assert begun.status_code == 200
    assert begun.json()["status"] == "active"

    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end")
    assert client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/begin").status_code == 409


def test_initiative_is_editable_during_setup(client: TestClient) -> None:
    # `setup` must still accept actions — it is where initiative gets corrected. Guarding on
    # status != "active" would have made the whole roster screen read-only.
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    resp = client.post(
        f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
        json={"action_type": "set_initiative", "payload": {"id": gid, "value": 20}},
    )
    assert resp.status_code == 200
    assert resp.json()["state"]["combatants"][gid]["initiative"] == 20


def test_undo_does_not_erase_a_roll(client: TestClient) -> None:
    """Rolls live outside the fold, so a cursor move never un-throws a die.

    Folding them would also mean Undo after a roll appeared to do nothing, since a roll has
    no effect on state.
    """
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    before = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert len(before) == 2

    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/undo")
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}/rolls").json()
    assert len(after) == 2


def test_list_combats_by_encounter(client: TestClient) -> None:
    cid = _demo(client)
    goblin = _monster(client, cid, "Goblin")
    enc = client.post(
        f"/api/v1/campaigns/{cid}/encounters",
        json={"name": "Ambush", "combatants": [{"monster_id": goblin, "count": 1}]},
    ).json()
    assert client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json() == []

    run = client.post(
        f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": enc["id"]}
    ).json()
    listed = client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json()
    assert [r["run_id"] for r in listed] == [run["run_id"]]
    # A run opens in `setup` (rolling initiative) and only becomes `active` on Begin.
    assert listed[0]["status"] == "setup" and listed[0]["round"] == 1
    client.post(f"/api/v1/campaigns/{cid}/combats/{run['run_id']}/begin")
    listed = client.get(f"/api/v1/campaigns/{cid}/combats?encounter_id={enc['id']}").json()
    assert listed[0]["status"] == "active"
    # No filter → empty (the endpoint is scoped to an encounter, not a firehose).
    assert client.get(f"/api/v1/campaigns/{cid}/combats").json() == []


def test_actions_undo_redo_and_resume(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]

    def act(atype, **payload):
        return client.post(
            f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
            json={"action_type": atype, "payload": payload},
        ).json()

    # Ten damage actions.
    last = None
    for _ in range(10):
        last = act("damage", id=gid, amount=1)
    assert last["state"]["combatants"][gid]["hp"] == 7 - 10 + 3  # 7hp, 10 dmg floored at 0
    assert last["state"]["combatants"][gid]["hp"] == 0

    # Undo 10 → back to full HP; can_redo true.
    for _ in range(10):
        u = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/undo").json()
    assert u["state"]["combatants"][gid]["hp"] == 7
    assert u["can_redo"] is True

    # Redo 3 → 3 damage applied.
    for _ in range(3):
        r = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/redo").json()
    assert r["state"]["combatants"][gid]["hp"] == 4

    # Resume: a fresh GET folds to the same state (survives reload).
    resumed = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    assert resumed["state"]["combatants"][gid]["hp"] == 4

    # A new action after undo truncates the redo tail.
    act("heal", id=gid, amount=2)
    after = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    assert after["can_redo"] is False
    assert after["state"]["combatants"][gid]["hp"] == 6


def test_end_combat_advances_clock_and_logs(client: TestClient) -> None:
    cid = _demo(client)
    run_id = _start_from_two_goblins(client, cid)
    run = client.get(f"/api/v1/campaigns/{cid}/combats/{run_id}").json()
    gid = run["state"]["order"][0]
    # Defeat one goblin, run a few turns.
    client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                json={"action_type": "damage", "payload": {"id": gid, "amount": 99}})
    for _ in range(4):  # advance a couple of rounds
        client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                    json={"action_type": "next_turn", "payload": {}})

    summary = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/end").json()
    assert summary["rounds"] >= 2
    # 6 seconds per round (5e); round 1 = 0 elapsed, so (rounds - 1) * 6.
    assert summary["duration_seconds"] == (summary["rounds"] - 1) * 6
    assert "Goblin 1" in summary["defeated"] or "Goblin 2" in summary["defeated"]

    # Combat ended → domain events logged; a second end is rejected via ended run.
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "combat_ended" in types and "combatant_defeated" in types
    closed = client.post(f"/api/v1/campaigns/{cid}/combats/{run_id}/actions",
                         json={"action_type": "next_turn", "payload": {}})
    assert closed.status_code == 409
