"""Seed the Curse of Strahd campaign with key NPCs.

Sourced from "Things to add in CoS/NPC.md". Runs over HTTP against the live
server (default http://127.0.0.1:8000) so it always hits the DB the running app
uses. Idempotent: an NPC whose name already exists in the campaign is skipped.

Usage:  python scripts/seed_cos_npcs.py [base_url]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
CAMPAIGN_NAME = "Curse of Strahd"

# (name, summary)
NPCS: list[tuple[str, str]] = [
    ("Stanimir",
     "Vistani elder and mage (Chaotic Neutral), loyal to Madame Eva; travels with his "
     "daughter Damia and son Ratka. The 'Mysterious Visitors' hook — lures the party to "
     "Barovia with his caravan and the Tale of the Prince."),
    ("Urwin Martikov",
     "Co-proprietor of the Blue Water Inn (Vallaki, N2) and a secret leader of the Keepers "
     "of the Feather, a wereraven faction resisting Strahd. Ally, info broker, and safe haven."),
    ("Danika Martikov",
     "Co-proprietor of the Blue Water Inn (Vallaki, N2) and a secret leader of the Keepers "
     "of the Feather wereravens. Ally and info broker alongside her husband Urwin."),
    ("Baron Vargas Vallakovich",
     "Delusional Burgomaster of Vallaki (N3). Enforces weekly mandatory festivals, believing "
     "forced happiness keeps Strahd's dread at bay. A central political actor in Vallaki."),
    ("Lady Fiona Wachter",
     "Noblewoman and Strahd sympathizer at Wachterhaus (N4), leading a local devil-worshiping "
     "cult. Plots to overthrow Baron Vallakovich and seize control of Vallaki."),
    ("Ismark \"The Lesser\" Kolyanovich",
     "Ireena's brother and the overwhelmed new Burgomaster of the Village of Barovia after "
     "their father's death. Recruits the party to escort Ireena to safety."),
    ("Victor Vallakovich",
     "The Baron's isolated, sinister son (N3t). A self-taught mage building a teleportation "
     "circle to escape Barovia — tested with lethal results on the household staff."),
    ("Stella Wachter",
     "Lady Fiona Wachter's daughter (N4q). After a disastrous courtship with Victor "
     "Vallakovich she suffered a psychological break and now believes she is a cat."),
    ("Sir Godfrey Gwilym",
     "A fallen revenant knight of the Order of the Silver Dragon at Argynvostholt (Q37). "
     "Unlike Vladimir Horngaard he keeps his sanity and goodness; a capable ally if recruited."),
    ("The Mad Mage of Mount Baratok",
     "A powerful wizard (canonically Mordenkainen) who lost his mind and spellbook after a "
     "failed rebellion against Strahd. Wanders Lake Zarovich, hostile and paranoid unless cured."),
    ("Emil Toranescu",
     "A werewolf pack leader imprisoned by Strahd in Castle Ravenloft's dungeons (K75a) after "
     "a leadership dispute engineered by his rival Kiril Stoyanovich."),
    ("Kiril Stoyanovich",
     "Brutal, power-hungry leader of the child-kidnapping werewolf pack (Z7). Loyal to Strahd; "
     "the primary antagonist of the werewolf-hunting subplot."),
    ("Morgantha",
     "A night hag at Old Bonegrinder (O4) posing as a kindly old woman selling addictive "
     "'Dream Pastries', using child abductions to fuel her coven's production."),
]


def _get(path: str) -> object:
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main() -> None:
    campaigns = _get("/api/v1/campaigns")
    match = next((c for c in campaigns if c["name"] == CAMPAIGN_NAME), None)
    if match is None:
        raise SystemExit(f"campaign {CAMPAIGN_NAME!r} not found; have: {[c['name'] for c in campaigns]}")
    cid = match["id"]

    existing = {e["name"] for e in _get(f"/api/v1/campaigns/{cid}/entities?entity_type=npc")}

    added = skipped = 0
    for name, summary in NPCS:
        if name in existing:
            skipped += 1
            continue
        _post(f"/api/v1/campaigns/{cid}/entities",
              {"entity_type": "npc", "name": name, "summary": summary})
        added += 1
        print(f"  + {name}")

    print(f"\nDone: {added} added, {skipped} already present.")


if __name__ == "__main__":
    main()
