"""Repair encounter combatants that point at monster IDs which no longer exist.

Why this exists
---------------
``Encounter.combatants_json`` stores an opaque ``monster_id`` with no foreign key. When the
bestiary was re-imported, the old monster rows were deleted and recreated under fresh IDs, so
91 of 110 Curse of Strahd encounters ended up referencing dead IDs. The API renders those as
``"(missing)"`` and silently drops them from difficulty math — the "encounters have no
creatures" symptom.

The old IDs are recoverable: a pre-reimport backup still holds the deleted ``monster`` rows,
which gives an exact ID -> name mapping. This script reads that mapping, resolves each name
against the live bestiary, and rewrites the combatant.

It also applies :data:`CANONICAL_CREATURE` — a curated set of corrections where the original
seed used a generic stand-in because the proper Curse of Strahd creature was missing from the
bestiary (all 79 CoS ``_copy`` variants failed to import until that bug was fixed).

Runs over HTTP against a running server rather than importing the app, matching every other
``seed_cos_*`` script: the editable install resolves the DB path through a OneDrive junction,
so an in-process run can silently target a different database file.

Usage::

    python scripts/relink_encounter_combatants.py --dry-run
    python scripts/relink_encounter_combatants.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

BASE = "http://127.0.0.1:8000"
DEFAULT_CAMPAIGN = "Curse of Strahd"
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP = BACKEND_ROOT / "backups" / "20260718T044330Z_manual" / "campaign_nexus.db"

#: Encounters whose combatants were seeded with a generic stand-in because the real Curse of
#: Strahd creature was missing from the bestiary. Keyed by encounter name; maps the
#: recovered (generic) monster name to the creature the module actually calls for.
#:
#: Curated by hand rather than matched heuristically — plenty of CoS encounters legitimately
#: use generic creatures (Berserkers, Dire Wolves, Shadows, Crawling Claws, the wilderness
#: Druid), and guessing would corrupt those.
CANONICAL_CREATURE: dict[str, dict[str, str]] = {
    "Angry Mob (Barovian Commoners)": {"Commoner": "Barovian Commoner"},
    "Random Encounter: Barovian Commoners": {"Commoner": "Barovian Commoner"},
    "Barovian Scouts": {"Scout": "Barovian Scout"},
    "Random Encounter: Barovian Scouts": {"Scout": "Barovian Scout"},
    "Vistani Bandits": {"Bandit": "Vistana Bandit"},
    "Castle Random: Vistani Thugs": {"Thug": "Vistana Thug"},
    "Vistani Thugs": {"Thug": "Vistana Thug"},
    "Castle Random: Trinket the Tiger": {"Saber-Toothed Tiger": "Armored Saber-Toothed Tiger"},
    "E1. Bildrath's Mercantile -- Parriwimple": {"Gladiator": "Parriwimple"},
    "K30. King's Accountant": {"Specter": "Lief Lipsiege"},
    "K62. Servants' Hall -- Cyrus Belview": {"Mongrelfolk": "Cyrus Belview"},
    "K75a. South Dungeon -- Emil Toranescu": {"Werewolf": "Emil Toranescu"},
    "K84. Catacombs -- Crypt 21: Patrina Velikovna": {"Banshee": "Patrina Velikovna"},
    "K84. Catacombs -- Crypt 39: Beucephalus": {"Nightmare": "Beucephalus"},
    "M. Base of Mount Baratok -- The Mad Mage": {"Archmage": "The Mad Mage of Mount Baratok"},
    "N1. St. Andral's Church -- Milivoj": {"Commoner": "Milivoj"},
    "Special: Dream Pastries -- Morgantha": {"Night Hag": "Morgantha"},
}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _request(method: str, url: str, body: Optional[dict[str, Any]] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code} on {method} {url}: {exc.read().decode(errors='replace')[:400]}")
    except urllib.error.URLError as exc:
        sys.exit(f"cannot reach {BASE} ({exc.reason}). Start the backend first.")


def _campaign_id(base: str, name: str) -> str:
    for c in _request("GET", f"{base}/api/v1/campaigns") or []:
        if isinstance(c, dict) and c.get("name") == name:
            return str(c["id"])
    sys.exit(f"campaign {name!r} not found")


def _live_bestiary(base: str, cid: str) -> tuple[dict[str, str], set[str]]:
    """``(name -> id, all ids)``. The high limit is required: the endpoint defaults to 200."""
    rows = _request("GET", f"{base}/api/v1/campaigns/{cid}/monsters?limit=100000") or []
    by_name: dict[str, str] = {}
    ambiguous: set[str] = set()
    ids: set[str] = set()
    for m in rows:
        if not isinstance(m, dict):
            continue
        ids.add(m["id"])
        if m["name"] in by_name:
            ambiguous.add(m["name"])
        by_name.setdefault(m["name"], m["id"])
    for name in ambiguous:
        print(f"  ! ambiguous bestiary name (using first): {name}")
    return by_name, ids


def _recovered_names(backup: Path) -> dict[str, str]:
    """Old monster ID -> name, read from a pre-reimport backup database."""
    if not backup.exists():
        sys.exit(f"backup database not found: {backup}")
    conn = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True)
    try:
        return {row[0]: row[1] for row in conn.execute("select id, name from monster")}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #
def _repair(
    encounter: dict[str, Any],
    old_names: dict[str, str],
    live_by_name: dict[str, str],
    live_ids: set[str],
    unresolved: list[str],
) -> Optional[list[dict[str, Any]]]:
    """Return rebuilt combatants, or ``None`` when the encounter needs no change."""
    name = encounter["name"]
    overrides = CANONICAL_CREATURE.get(name, {})
    combatants = encounter.get("combatants") or []
    rebuilt: list[dict[str, Any]] = []
    changed = False

    for spec in combatants:
        monster_id = spec["monster_id"]
        # An encounter can be half-broken, and a live ID may still be the wrong creature,
        # so resolve the intended name for every combatant, not just the dangling ones.
        current = spec.get("name") if monster_id in live_ids else old_names.get(monster_id)
        wanted = overrides.get(current or "", current)

        if wanted is None:
            unresolved.append(f"{name}: unknown monster id {monster_id}")
            rebuilt.append(dict(spec))
            continue

        new_id = live_by_name.get(wanted)
        if new_id is None:
            unresolved.append(f"{name}: no bestiary entry named {wanted!r}")
            rebuilt.append(dict(spec))
            continue

        if new_id != monster_id:
            changed = True
        # count and side are authored data — carry them through untouched.
        rebuilt.append({
            "monster_id": new_id,
            "monster_name": wanted,
            "count": int(spec.get("count", 1)),
            "side": spec.get("side", "foe"),
        })

    return rebuilt if changed else None


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP,
                        help="database holding the pre-reimport monster rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cid = _campaign_id(args.base, args.campaign)
    old_names = _recovered_names(args.backup)
    live_by_name, live_ids = _live_bestiary(args.base, cid)
    print(f"campaign {args.campaign} ({cid})")
    print(f"  {len(old_names)} recovered names, {len(live_ids)} live monsters")

    encounters = _request("GET", f"{args.base}/api/v1/campaigns/{cid}/encounters") or []
    unresolved: list[str] = []
    planned: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    for enc in encounters:
        rebuilt = _repair(enc, old_names, live_by_name, live_ids, unresolved)
        if rebuilt is not None:
            planned.append((enc, rebuilt))

    if unresolved:
        # Never guess: a wrong creature is worse than a visibly missing one.
        print(f"\n{len(unresolved)} unresolved reference(s):")
        for line in unresolved:
            print(f"  ! {line}")
        sys.exit("aborting without changes — resolve the above first")

    print(f"  {len(planned)} encounter(s) need repair")
    for enc, rebuilt in planned:
        summary = ", ".join(f"{c['count']}x {c['monster_name']}" for c in rebuilt)
        print(f"    {enc['name']}: {summary}")
        if not args.dry_run:
            _request("PATCH", f"{args.base}/api/v1/campaigns/{cid}/encounters/{enc['id']}",
                     {"combatants": rebuilt})

    print(f"\n{'[dry-run] would repair' if args.dry_run else 'repaired'} {len(planned)} encounter(s)")


if __name__ == "__main__":
    main()
