"""Seed a Barovia roadway random-encounter table for the Curse of Strahd campaign.

This creates a d20 "Barovia Road Encounters" random table whose rows link to encounter
entities, so rolling it on the table's page jumps straight to the encounter to run. It is an
*original* travel table — standard Monster Manual creatures with our own brief descriptions,
not a transcription of any published table — meant as a starting scaffold. Tune the ranges,
swap creatures, and add combatants from the Bestiary using the in-app table/encounter editors.

Runs over HTTP against a running backend (same rationale as ``seed_into_the_mists``: the app is
installed editable through a OneDrive junction, so importing it in a throwaway process can hit a
different copy of the database). Start the backend first, then::

    python scripts/seed_cos_encounters.py
    python scripts/seed_cos_encounters.py --base http://127.0.0.1:8000 --campaign "Curse of Strahd"

Idempotent: re-running matches encounters and the table by name and updates them in place.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

TABLE_NAME = "Barovia Road Encounters"
TABLE_DICE = "1d20"

# Each entry becomes an encounter entity; ``lo``/``hi`` place it on the d20 table. Descriptions
# and tactics are original one-liners; creatures are generic Monster Manual references the GM
# can wire up from the Bestiary. ``target`` False means the row is a flavour result with no
# encounter to run (the quiet road).
ROAD_ENCOUNTERS = [
    {"lo": 1, "hi": 6, "name": "The Quiet Road", "target": False,
     "tactics": "No encounter. The mists press close and birdsong dies, but nothing comes — yet."},
    {"lo": 7, "hi": 9, "name": "Barovian Wolves", "terrain": "forest road",
     "tactics": "A pack shadows the party from the treeline, testing stragglers before it commits."},
    {"lo": 10, "hi": 11, "name": "Dire Wolf Hunter", "terrain": "forest road",
     "tactics": "A lone dire wolf drives the party toward waiting pack-mates or a drop."},
    {"lo": 12, "hi": 12, "name": "Wereraven Watcher", "terrain": "open road",
     "tactics": "A raven trails overhead — a Keeper of the Feather sizing the party up, hostile only if cornered."},
    {"lo": 13, "hi": 13, "name": "Vistani on the Road", "terrain": "roadside camp",
     "tactics": "A small Vistani band shares a fire; a reading, a warning, or a trap depending on their loyalties."},
    {"lo": 14, "hi": 14, "name": "The Rising Dead", "terrain": "roadside graves",
     "tactics": "Zombies claw up from unmarked graves and shamble toward torchlight."},
    {"lo": 15, "hi": 15, "name": "Blights in the Pines", "terrain": "dark woods",
     "tactics": "Needle blights hold still as saplings until the party is surrounded, then loose a volley."},
    {"lo": 16, "hi": 16, "name": "Dusk Bat Swarm", "terrain": "open road at dusk",
     "tactics": "A swarm of bats boils out of the gloom, blinding and scattering mounts."},
    {"lo": 17, "hi": 17, "name": "Luring Lights", "terrain": "fog-bound moor",
     "tactics": "Will-o'-wisps drift just off the road, coaxing travellers into the mire."},
    {"lo": 18, "hi": 18, "name": "The Mad Hermit", "terrain": "ruined shrine",
     "tactics": "A broken hermit mage mistakes the party for tormentors and lashes out with frightened magic."},
    {"lo": 19, "hi": 19, "name": "The Ghostly Wagon", "target": True, "terrain": "open road",
     "tactics": "A funeral wagon rolls past driven by no one — an omen, not a fight, unless disturbed."},
    {"lo": 20, "hi": 20, "name": "The Revenant's Hunt", "terrain": "crossroads",
     "tactics": "A revenant stalks the road toward the one who wronged it, sparing anyone who does not stand in its way."},
]


def _request(method: str, url: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 - localhost dev tooling
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


def _upsert_encounter(base: str, cid: str, existing: dict[str, str], spec: dict) -> str:
    """Return the encounter id for ``spec['name']``, creating it if absent (idempotent by name)."""
    name = spec["name"]
    if name in existing:
        return existing[name]
    body = {"name": name, "terrain": spec.get("terrain"), "tactics": spec.get("tactics"),
            "combatants": []}
    created = _request("POST", f"{base}/api/v1/campaigns/{cid}/encounters", body)
    assert isinstance(created, dict)
    print(f"  + encounter '{name}' ({created['id']})")
    return created["id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="backend base URL")
    parser.add_argument("--campaign", default="Curse of Strahd", help="target campaign name")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    cid = _find_campaign(base, args.campaign)

    existing_encs = {
        e["name"]: e["id"]
        for e in _request("GET", f"{base}/api/v1/campaigns/{cid}/encounters")
        if isinstance(e, dict)
    }

    rows = []
    for spec in ROAD_ENCOUNTERS:
        wants_target = spec.get("target", True)
        target_id = _upsert_encounter(base, cid, existing_encs, spec) if wants_target else None
        rows.append({
            "min": spec["lo"], "max": spec["hi"], "text": spec["tactics"],
            "target_entity_id": target_id,
        })

    tables_url = f"{base}/api/v1/campaigns/{cid}/random-tables"
    existing = _request("GET", tables_url)
    assert isinstance(existing, list)
    match = next((t for t in existing if t["name"] == TABLE_NAME), None)

    payload = {"name": TABLE_NAME, "dice": TABLE_DICE, "rows": rows}
    if match is None:
        result = _request("POST", tables_url, payload)
        assert isinstance(result, dict)
        print(f"created table '{TABLE_NAME}' ({result['id']}) with {result['row_count']} rows")
    else:
        result = _request("PATCH", f"{tables_url}/{match['id']}", payload)
        assert isinstance(result, dict)
        print(f"updated table '{TABLE_NAME}' ({result['id']}) with {result['row_count']} rows")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
