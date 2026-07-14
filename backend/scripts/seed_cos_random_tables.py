"""Seed the Curse of Strahd random-encounter tables (the user's own purchased content).

Creates the five roll tables from the module's random-encounter rules and wires each row that
is an actual fight to an encounter entity pre-stocked with matching Bestiary creatures, so a
roll jumps straight to a runnable encounter:

  * Barovia — Wilderness & Roads (Daytime)     d12+d8, results 2-20
  * Barovia — Wilderness & Roads (Nighttime)   d12+d8, results 2-20
  * Castle Ravenloft                            d12+d8, results 2-20
  * Village of Barovia — Abandoned Houses       d20, ranged
  * Vallaki — Unmarked Houses                   d20, ranged

Trigger rules (applied by the GM, not encoded here): on a road check every 30 min, encounter on
d20 ≥ 18; in the wilderness d20 ≥ 15 (max two per 12h outdoors). Castle Ravenloft: on entering an
unoccupied area and every 10 min resting, encounter on d20 ≥ 18. The house tables are rolled on
entering an unmarked residence. Creature counts on the encounters are representative averages of
the module's dice (e.g. 3d6 wolves → 10); adjust per fight.

Runs over HTTP against a running backend (same rationale as ``seed_into_the_mists``). Start the
backend first, then::

    python scripts/seed_cos_random_tables.py
    python scripts/seed_cos_random_tables.py --base http://127.0.0.1:8000 --campaign "Curse of Strahd"

Idempotent: encounters and tables are matched by name and updated in place, never duplicated.
``--replace-scaffold`` also removes the earlier placeholder "Barovia Road Encounters" table and
its stub encounters from the first pass.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# Encounters: name -> (terrain, tactics, [(monster_name, count), ...]). Reused across tables.
# Counts are representative averages of the module's dice. Monsters resolve against the
# campaign Bestiary by name; any not found are skipped (encounter still created + linkable).
# --------------------------------------------------------------------------- #
ENCOUNTERS: dict[str, dict] = {
    "Angry Mob (Barovian Commoners)": {
        "terrain": "road",
        "tactics": "Torches and pitchforks (+2 to hit, 1d6). A mob bound for the castle or a "
                   "fleeing family; evadable by stealth.",
        "monsters": [("Commoner", 10)],
    },
    "Barovian Scouts": {
        "tactics": "Hunters/trappers seeking a missing person; light crossbows; friendly if "
                   "unprovoked.",
        "monsters": [("Scout", 3)],
    },
    "Vistani Bandits": {
        "tactics": "Servants of Strahd. Will guide the party for 100 gp (drops later checks to "
                   "d12). One carries 2d4 gems (50 gp each).",
        "monsters": [("Bandit", 3)],
    },
    "Skeletal Rider": {
        "tactics": "Skeleton on a warhorse skeleton in ruined chain mail, carrying an unlit "
                   "lantern; ignores the party unless attacked.",
        "monsters": [("Skeleton", 1), ("Warhorse Skeleton", 1)],
    },
    "Wereraven & Raven Swarms": {
        "tactics": "In raven form. If left unmolested they watch the party and aid them in later "
                   "fights.",
        "monsters": [("Wereraven", 1), ("Swarm of Ravens", 2)],
    },
    "Dire Wolves": {
        "terrain": "light fog",
        "tactics": "Overgrown servants of Strahd; immune to charm and fright.",
        "monsters": [("Dire Wolf", 3)],
    },
    "Wolves": {
        "tactics": "Loyal to Strahd; immune to charm and fright; attack after a few minutes of "
                   "signaling howls.",
        "monsters": [("Wolf", 10)],
    },
    "Berserkers": {
        "tactics": "Mountain folk caked in gray mud (+3 Stealth); shun civilization and attack "
                   "only if cornered.",
        "monsters": [("Berserker", 2)],
    },
    "Werewolves": {
        "tactics": "Pose as trappers; probe for silvered weapons and attack in hybrid form if "
                   "none are found (in wolf form at night, surprising a resting party).",
        "monsters": [("Werewolf", 3)],
    },
    "Druid & Twig Blights": {
        "tactics": "Blights fight to the death; the druid flees toward Yester Hill below half HP.",
        "monsters": [("Druid", 1), ("Twig Blight", 7)],
    },
    "Needle Blights": {
        "terrain": "forest",
        "tactics": "The druids' forest patrol; bypassable by stealth without light.",
        "monsters": [("Needle Blight", 5)],
    },
    "Scarecrows": {
        "tactics": "Baba Lysaga's evil-imbued scarecrows; surprise the party unless a PC has "
                   "passive Perception 11+.",
        "monsters": [("Scarecrow", 3)],
    },
    "Revenant": {
        "tactics": "Fallen knight of the Order of the Silver Dragon. Hostile if mistaken for a "
                   "minion of Strahd; otherwise directs the party to Argynvostholt.",
        "monsters": [("Revenant", 1)],
    },
    "Ghost (Strahd's Victim)": {
        "tactics": "Apparition of a drained victim; tries to possess a PC and force them off the "
                   "cliffs of Castle Ravenloft.",
        "monsters": [("Ghost", 1)],
    },
    "Swarms of Bats": {
        "tactics": "Servants of Strahd; attack immediately without provocation.",
        "monsters": [("Swarm of Bats", 4)],
    },
    "Zombie Mob": {
        "tactics": "A ravenous mob of decaying Barovians; avoidable by stealth without light.",
        "monsters": [("Zombie", 10)],
    },
    "Strahd Zombies": {
        "tactics": "Undead former castle guards in tattered livery; severed limbs keep attacking. "
                   "Avoidable by stealth.",
        "monsters": [("Strahd Zombie", 4)],
    },
    "Will-o'-Wisp Lure": {
        "tactics": "A wisp lures the party to a ruined tower (desecrated ground). Disturbing the "
                   "chest erupts 3d6 zombies and the wisp joins. Occurs once — add the wisp "
                   "manually (not in the SRD Bestiary).",
        "monsters": [("Zombie", 10)],
    },
    # --- Castle Ravenloft ---
    "Ezmerelda d'Avenir": {
        "tactics": "Invisible (greater invisibility), investigating the castle. Identifies "
                   "herself if approached peacefully and can join the party. Occurs once.",
        "monsters": [("Ezmerelda d'Avenir", 1)],
    },
    "Rahadin": {
        "tactics": "'The master wishes to see you' — directs the party to a random room (d6). "
                   "Fights to the death if attacked.",
        "monsters": [("Rahadin", 1)],
    },
    "Black Cat (Familiar)": {
        "tactics": "A witch's familiar; hisses and flees, attacking only if cornered.",
        "monsters": [("Cat", 1)],
    },
    "Broom of Animated Attack": {
        "tactics": "Sweeps autonomously through the shadows; strikes when a PC comes within 5 ft.",
        "monsters": [("Broom of Animated Attack", 1)],
    },
    "Flying Swords": {
        "tactics": "Rusty blades adrift in the corridors; hostile to all intruders (blindsight).",
        "monsters": [("Flying Sword", 3)],
    },
    "Crawling Claws": {
        "tactics": "Severed mummified hands; one sneaks into a backpack (Stealth vs passive "
                   "Perception) to surprise-attack during a long rest.",
        "monsters": [("Crawling Claw", 7)],
    },
    "Shadows": {
        "tactics": "Undead shadows tail the party silently; attack only if provoked or commanded "
                   "by Strahd.",
        "monsters": [("Shadow", 3)],
    },
    "Crawling Strahd Zombie": {
        "tactics": "Severed at the waist (15 HP); drags itself forward, groaning.",
        "monsters": [("Strahd Zombie", 1)],
    },
    "Vistani Thugs": {
        "tactics": "Claim to be escaped captives offering alliance; betray the party when Strahd "
                   "appears. One carries 2d8 gems (50 gp each).",
        "monsters": [("Thug", 3)],
    },
    "Wights (Guard Captains)": {
        "tactics": "Former guard captains in tattered livery; hostile on sight. Carry "
                   "Barovian-crest longswords and 2d20 ep bearing Strahd's visage.",
        "monsters": [("Wight", 2)],
    },
    "Giant Spider Cocoon": {
        "tactics": "A cocoon webbed to the ceiling; cutting it open reveals one of six things "
                   "(d6) — often a hostile creature.",
        "monsters": [("Giant Spider", 1)],
    },
    "Barovian Witch": {
        "tactics": "Crone from area K56 seeking her cat familiar; attacks with magic "
                   "immediately. Occurs once.",
        "monsters": [("Barovian Witch", 1)],
    },
    "Vampire Spawn": {
        "tactics": "Former adventurers turned minions; spider-climb the ceiling and drop to "
                   "surprise the party (passive Perception 16+ to notice).",
        "monsters": [("Vampire Spawn", 3)],
    },
    "Strahd von Zarovich": {
        "tactics": "Appears with a thunderclap; surprises any PC with passive Perception under "
                   "19, toys with a target for a few rounds, then vanishes.",
        "monsters": [("Strahd von Zarovich", 1)],
    },
    # --- Houses ---
    "Swarms of Rats": {
        "tactics": "Servants of Strahd; hide in dark corners and attack if the interior is "
                   "actively searched.",
        "monsters": [("Swarm of Rats", 4)],
    },
    "Vallakian Cultists": {
        "tactics": "Devil-worshippers under Lady Fiona Wachter; hostile if their rituals or "
                   "sanctuary are disrupted.",
        "monsters": [("Cultist", 5), ("Cult Fanatic", 1)],
    },
}


def _row(lo: int, hi: int, text: str, enc: str | None = None) -> dict:
    return {"lo": lo, "hi": hi, "text": text, "enc": enc}


# result -> (text, encounter-name-or-None). d12+d8 tables: one row per value 2..20.
WILDERNESS_DAY = [
    _row(2, 2, "3d6 Barovian commoners — an angry mob (torches & pitchforks) or a fleeing family; evadable by stealth.", "Angry Mob (Barovian Commoners)"),
    _row(3, 3, "1d6 Barovian scouts — hunters seeking a missing person; friendly if unprovoked.", "Barovian Scouts"),
    _row(4, 4, "Hunting trap — a front-rank PC makes DC 15 Wis (Survival) or a random PC triggers a steel trap.", None),
    _row(5, 5, "Grave — 25% intact (a skeletal soldier in rusted chain mail); 75% a violated mud hole.", None),
    _row(6, 6, "False trail — druid-made, ending at a concealed spiked pit covered by twigs and needles.", None),
    _row(7, 7, "1d4+1 Vistani bandits — Strahd's servants; will guide the party for 100 gp. One carries 2d4 gems (50 gp).", "Vistani Bandits"),
    _row(8, 8, "Skeletal rider — a skeleton and warhorse skeleton with an unlit lantern; ignores the party unless attacked.", "Skeletal Rider"),
    _row(9, 9, "Trinket — a random PC finds a lost item from the Trinkets table on the ground.", None),
    _row(10, 10, "Hidden bundle — drab adult human clothes wrapped in leather in a log (a werewolf's or wereraven's).", None),
    _row(11, 11, "1d4 swarms of ravens (50%) or 1 wereraven (50%) — in raven form; watch and later aid the party if unmolested.", "Wereraven & Raven Swarms"),
    _row(12, 12, "1d6 dire wolves — Strahd's servants; immune to charm and fright; light fog.", "Dire Wolves"),
    _row(13, 13, "3d6 wolves — loyal to Strahd; immune to charm and fright; attack after signaling howls.", "Wolves"),
    _row(14, 14, "1d4 berserkers — mud-caked mountain folk (+3 Stealth); attack only if cornered.", "Berserkers"),
    _row(15, 15, "Corpse — d6: 1-2 a wolf slain by bolts; 3-5 a Barovian torn by dire wolves; 6 an illusory duplicate of a PC (melts to a skeleton if moved).", None),
    _row(16, 16, "1d6 werewolves — posing as trappers; probe for silvered weapons and attack in hybrid form if none are found.", "Werewolves"),
    _row(17, 17, "1 druid with 2d6 twig blights — blights fight to the death; the druid flees to Yester Hill below half HP.", "Druid & Twig Blights"),
    _row(18, 18, "2d4 needle blights — the druids' forest patrol; bypassable by stealth without light.", "Needle Blights"),
    _row(19, 19, "1d6 scarecrows — Baba Lysaga's; surprise unless a PC has passive Perception 11+.", "Scarecrows"),
    _row(20, 20, "1 revenant — a fallen Silver Dragon knight; directs the party to Argynvostholt unless mistaken for Strahd's minion.", "Revenant"),
]

WILDERNESS_NIGHT = [
    _row(2, 2, "1 ghost — a victim drained by Strahd; tries to possess a PC and force them off the castle cliffs.", "Ghost (Strahd's Victim)"),
    _row(3, 3, "Hunting trap — as the daytime table.", None),
    _row(4, 4, "Grave — as the daytime table.", None),
    _row(5, 5, "Trinket — as the daytime table.", None),
    _row(6, 6, "Corpse — as the daytime table.", None),
    _row(7, 7, "Hidden bundle — as the daytime table.", None),
    _row(8, 8, "Skeletal rider — as the daytime table.", "Skeletal Rider"),
    _row(9, 9, "1d8 swarms of bats — Strahd's servants; attack immediately.", "Swarms of Bats"),
    _row(10, 10, "1d6 dire wolves — as the daytime table.", "Dire Wolves"),
    _row(11, 11, "3d6 wolves — as the daytime table.", "Wolves"),
    _row(12, 12, "1d4 berserkers — as the daytime table.", "Berserkers"),
    _row(13, 13, "1 druid and 2d6 twig blights — as the daytime table.", "Druid & Twig Blights"),
    _row(14, 14, "2d4 needle blights — as the daytime table.", "Needle Blights"),
    _row(15, 15, "1d6 werewolves — in wolf form; stalk the party and surprise-attack during a rest or when weakened.", "Werewolves"),
    _row(16, 16, "3d6 zombies — a ravenous mob of Barovian dead; avoidable by stealth without light.", "Zombie Mob"),
    _row(17, 17, "1d6 scarecrows — as the daytime table.", "Scarecrows"),
    _row(18, 18, "1d8 Strahd zombies — former castle guards; severed limbs keep attacking; avoidable by stealth.", "Strahd Zombies"),
    _row(19, 19, "1 will-o'-wisp (once) — lures the party to a ruined tower; disturbing the chest erupts 3d6 zombies and the wisp joins.", "Will-o'-Wisp Lure"),
    _row(20, 20, "1 revenant — as the daytime table.", "Revenant"),
]

CASTLE = [
    _row(2, 2, "Ezmerelda d'Avenir (once) — invisible; identifies herself if approached peacefully and can join the party.", "Ezmerelda d'Avenir"),
    _row(3, 3, "Rahadin — 'The master wishes to see you'; directs the party to a random room (d6); fights to the death if attacked.", "Rahadin"),
    _row(4, 4, "1 black cat — a witch's familiar; hisses and flees, attacking only if cornered.", "Black Cat (Familiar)"),
    _row(5, 5, "1 broom of animated attack — sweeps through the shadows and strikes when a PC comes within 5 ft.", "Broom of Animated Attack"),
    _row(6, 6, "1d4+1 flying swords — rusty blades adrift in the corridors; hostile to all (blindsight).", "Flying Swords"),
    _row(7, 7, "Blinsky toy (if moving) — a creepy toy tagged 'Is No Fun, Is No Blinsky!' (roll d6 for which).", None),
    _row(8, 8, "Unseen servant — carries a random item (d6); one option is a dinner bell that summons 1d4 vampire spawn.", None),
    _row(9, 9, "1d4 commoners — villagers with torches: 'Kill the vampire!' While escorting the party, later encounters occur on d20 ≥ 9.", "Angry Mob (Barovian Commoners)"),
    _row(10, 10, "2d6 crawling claws — one sneaks into a backpack to surprise-attack during a long rest.", "Crawling Claws"),
    _row(11, 11, "1d6 shadows — tail the party silently; attack only if provoked or ordered by Strahd.", "Shadows"),
    _row(12, 12, "1d6 swarms of bats — Strahd's servants; instantly hostile.", "Swarms of Bats"),
    _row(13, 13, "1 crawling Strahd zombie — severed at the waist (15 HP); drags itself forward, groaning.", "Crawling Strahd Zombie"),
    _row(14, 14, "1d4+1 Vistani thugs — feign being freed captives; betray the party when Strahd appears. One carries 2d8 gems (50 gp).", "Vistani Thugs"),
    _row(15, 15, "1d4 wights — former guard captains; hostile on sight; carry Barovian-crest longswords and 2d20 ep.", "Wights (Guard Captains)"),
    _row(16, 16, "Trinket — a PC kicks up a lost item from the Trinkets table in the dust.", None),
    _row(17, 17, "Giant spider cocoon — webbed to the ceiling; cutting it open reveals one of six things (d6), often hostile.", "Giant Spider Cocoon"),
    _row(18, 18, "1 Barovian witch (once) — from area K56, seeking her cat; attacks with magic immediately.", "Barovian Witch"),
    _row(19, 19, "1d4+1 vampire spawn — spider-climb the ceiling and drop to surprise the party (passive Perception 16+ to notice).", "Vampire Spawn"),
    _row(20, 20, "Strahd von Zarovich — appears with a thunderclap; surprises PCs under passive Perception 19, toys with them, then vanishes.", "Strahd von Zarovich"),
]

VILLAGE_HOUSES = [
    _row(1, 3, "None — an empty structure.", None),
    _row(4, 8, "2d4 swarms of rats — Strahd's servants; hide in dark corners and attack if the interior is explored.", "Swarms of Rats"),
    _row(9, 16, "Barovian villagers — 1d4 adults and 1d8-1 children; cower by candlelight and refuse outsiders.", None),
    _row(17, 20, "2d4 Strahd zombies — reeking of decay; converge on the party when a door or shutter opens.", "Strahd Zombies"),
]

VALLAKI_HOUSES = [
    _row(1, 3, "None — an empty structure.", None),
    _row(4, 5, "2d4 swarms of rats — Strahd's servants; hostile if the house is searched.", "Swarms of Rats"),
    _row(6, 18, "Vallakian townsfolk — 1d4 adults and 1d8-1 children; speak only from behind doors; terrified of the burgomaster and Strahd.", None),
    _row(19, 20, "2d4 cultists led by 1 cult fanatic — devil-worshippers under Lady Wachter; hostile if their rites are disrupted.", "Vallakian Cultists"),
]

TABLES = [
    ("Barovia — Wilderness & Roads (Daytime)", "d12+d8", WILDERNESS_DAY),
    ("Barovia — Wilderness & Roads (Nighttime)", "d12+d8", WILDERNESS_NIGHT),
    ("Castle Ravenloft", "d12+d8", CASTLE),
    ("Village of Barovia — Abandoned Houses", "1d20", VILLAGE_HOUSES),
    ("Vallaki — Unmarked Houses", "1d20", VALLAKI_HOUSES),
]

# The placeholder table + stub encounters from the first (pre-purchase) scaffold pass.
SCAFFOLD_TABLE = "Barovia Road Encounters"
SCAFFOLD_ENCOUNTERS = [
    "Barovian Wolves", "Dire Wolf Hunter", "Wereraven Watcher", "Vistani on the Road",
    "The Rising Dead", "Blights in the Pines", "Dusk Bat Swarm", "Luring Lights",
    "The Mad Hermit", "The Ghostly Wagon", "The Revenant's Hunt",
]


def _request(method: str, url: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {url} ({exc}); is the backend running?") from exc


def _find_campaign(base: str, name: str) -> str:
    campaigns = _request("GET", f"{base}/api/v1/campaigns")
    assert isinstance(campaigns, list)
    for camp in campaigns:
        if camp["name"] == name:
            return camp["id"]
    created = _request(
        "POST", f"{base}/api/v1/campaigns",
        {"name": name, "description": "Curse of Strahd.", "rule_system_id": "dnd5e"},
    )
    assert isinstance(created, dict)
    print(f"created campaign '{name}' ({created['id']})")
    return created["id"]


def _monster_map(base: str, cid: str) -> dict[str, str]:
    monsters = _request("GET", f"{base}/api/v1/campaigns/{cid}/monsters")
    assert isinstance(monsters, list)
    return {m["name"]: m["id"] for m in monsters if isinstance(m, dict)}


def _ensure_encounters(base: str, cid: str, monsters: dict[str, str]) -> dict[str, str]:
    """Create each named encounter (with resolved combatants) if absent; return name -> id."""
    existing = {
        e["name"]: e["id"]
        for e in _request("GET", f"{base}/api/v1/campaigns/{cid}/encounters")
        if isinstance(e, dict)
    }
    ids: dict[str, str] = {}
    for name, spec in ENCOUNTERS.items():
        if name in existing:
            ids[name] = existing[name]
            continue
        combatants = []
        for mname, count in spec.get("monsters", []):
            mid = monsters.get(mname)
            if mid is None:
                print(f"    ! no Bestiary match for '{mname}' — skipped in '{name}'")
                continue
            combatants.append({"monster_id": mid, "count": count, "side": "foe"})
        created = _request(
            "POST", f"{base}/api/v1/campaigns/{cid}/encounters",
            {"name": name, "terrain": spec.get("terrain"), "tactics": spec.get("tactics"),
             "combatants": combatants},
        )
        assert isinstance(created, dict)
        ids[name] = created["id"]
        print(f"  + encounter '{name}' ({len(combatants)} combatant group(s))")
    return ids


def _upsert_table(base: str, cid: str, name: str, dice: str, spec_rows: list[dict],
                  enc_ids: dict[str, str]) -> None:
    rows = [
        {"min": r["lo"], "max": r["hi"], "text": r["text"],
         "target_entity_id": enc_ids.get(r["enc"]) if r["enc"] else None}
        for r in spec_rows
    ]
    tables_url = f"{base}/api/v1/campaigns/{cid}/random-tables"
    existing = _request("GET", tables_url)
    assert isinstance(existing, list)
    match = next((t for t in existing if t["name"] == name), None)
    payload = {"name": name, "dice": dice, "rows": rows}
    if match is None:
        result = _request("POST", tables_url, payload)
        verb = "created"
    else:
        result = _request("PATCH", f"{tables_url}/{match['id']}", payload)
        verb = "updated"
    assert isinstance(result, dict)
    print(f"  {verb} table '{name}' — {result['row_count']} rows ({dice})")


def _remove_scaffold(base: str, cid: str) -> None:
    tables = _request("GET", f"{base}/api/v1/campaigns/{cid}/random-tables")
    assert isinstance(tables, list)
    for t in tables:
        if t["name"] == SCAFFOLD_TABLE:
            _request("DELETE", f"{base}/api/v1/campaigns/{cid}/random-tables/{t['id']}")
            print(f"  - removed scaffold table '{SCAFFOLD_TABLE}'")
    encounters = _request("GET", f"{base}/api/v1/campaigns/{cid}/encounters")
    assert isinstance(encounters, list)
    for e in encounters:
        if e["name"] in SCAFFOLD_ENCOUNTERS:
            _request("DELETE", f"{base}/api/v1/campaigns/{cid}/entities/{e['id']}")
            print(f"  - removed scaffold encounter '{e['name']}'")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="backend base URL")
    parser.add_argument("--campaign", default="Curse of Strahd", help="target campaign name")
    parser.add_argument("--replace-scaffold", action="store_true",
                        help="also delete the earlier placeholder table + stub encounters")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    cid = _find_campaign(base, args.campaign)
    if args.replace_scaffold:
        _remove_scaffold(base, cid)

    monsters = _monster_map(base, cid)
    print(f"bestiary: {len(monsters)} creatures available for combatant matching")
    enc_ids = _ensure_encounters(base, cid, monsters)
    print(f"encounters ready: {len(enc_ids)}")

    for name, dice, rows in TABLES:
        _upsert_table(base, cid, name, dice, rows, enc_ids)
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
