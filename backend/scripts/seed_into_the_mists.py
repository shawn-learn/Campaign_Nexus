"""Seed the Curse of Strahd "Into the Mists" fog skill challenge (chapter 01).

This is the reference use of the generalizable skill-challenge feature: the graduated
"Choking Fog" scene from *Into the Mists*, authored for D&D 5e (no Nimble conversion — the
wolves' 5e stat blocks and the encounter itself are untouched; only the fog challenge is
modelled here).

It runs over HTTP against a running backend so it always writes the same database the server
uses — the app is installed editable through a OneDrive junction, so importing the app in a
throwaway process can resolve paths to a *different* copy of the database. Start the backend
(``uvicorn app.main:app``) first, then::

    python scripts/seed_into_the_mists.py              # 127.0.0.1:8000, campaign "Curse of Strahd"
    python scripts/seed_into_the_mists.py --base http://127.0.0.1:8000 --campaign "Curse of Strahd"

Idempotent: re-running updates the existing challenge in place rather than duplicating it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

CHALLENGE_NAME = "The Choking Fog"

PREMISE = (
    "As the fog closes around you, the air grows cold and still. The Mists tighten, "
    "spiraling upward like a living wall of grey. Run this after 5 total checks, using "
    "whichever approaches the players take; track total failures and read the outcome below."
)

# The chapter's "Skill Use Guidance" — Easy / Normal / Difficult map onto the canonical tiers.
APPROACHES = [
    {"skill": "Perception", "difficulty": "easy",
     "hint": "Detect the unnatural stillness — birdsong dying, vanishing footprints."},
    {"skill": "Insight", "difficulty": "normal",
     "hint": "Realize the fog is reactive, not natural."},
    {"skill": "Survival", "difficulty": "normal",
     "hint": "Hold a straight line as landmarks repeat — the same stump, the same wagon."},
    {"skill": "Arcana", "difficulty": "hard",
     "hint": "Identify planar distortion or demiplane manipulation."},
    {"skill": "Religion", "difficulty": "hard",
     "hint": "Sense the seal beneath the curse — something older than Strahd."},
]

# Graduated outcomes keyed on total failures across the 5 checks (chapter §3).
OUTCOMES = [
    {"min_failures": 0, "label": "Exceptional Success",
     "narrative": "The party reads the mist's patterns and moves with perfect cohesion.",
     "effects": [
         "They spot the wolves early",
         "Player's choice: a surprise round, advantage on initiative, or avoid the Wolf "
         "Ambush entirely",
         "On a critical success, a voice like cracking bone: “The first seal bends.”",
     ]},
    {"min_failures": 1, "label": "Strong Success",
     "narrative": "The party stumbles once, but quickly regains control.",
     "effects": ["Normal Wolf Ambush", "No penalties"]},
    {"min_failures": 2, "label": "Minor Complication",
     "narrative": "Direction bends; the fog presses close.",
     "effects": [
         "Heroes start the Wolf Ambush 2 spaces out of formation",
         "One hero makes a WIS save (DC 15) or is dazed for 1 round",
     ]},
    {"min_failures": 3, "label": "Moderate Consequence",
     "narrative": "The fog manipulates space with intent. The fog seems to breathe.",
     "effects": [
         "Wolves begin in optimal tactical positions (DM chooses)",
         "Wolves deal +1 damage in the first round",
     ]},
    {"min_failures": 4, "label": "Severe Consequence",
     "narrative": "The mist invades the heroes' senses.",
     "effects": [
         "Party starts combat slowed for 1 round",
         "Wolves have advantage in the first round",
         "One hero sees a flash of vision: a skeletal hand touching the fog",
         "Consider the Very Difficult encounter variant",
     ]},
    {"min_failures": 5, "label": "Catastrophic Consequence",
     "narrative": "The mists claim a toll. The fog whispers clearly: “Welcome home.”",
     "effects": [
         "Party begins surrounded in the worst possible terrain",
         "Wolves automatically take the first turn",
         "Wolves deal +2 damage in round one",
         "Use the Very Difficult encounter variant — this is the second Vecna breadcrumb",
     ]},
]

CHALLENGE_BODY = {
    "name": CHALLENGE_NAME,
    "premise": PREMISE,
    "total_checks": 5,
    "approaches": APPROACHES,
    "outcomes": OUTCOMES,
}


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
            if camp["rule_system_id"] != "dnd5e":
                raise SystemExit(
                    f"campaign '{name}' uses {camp['rule_system_id']}, not dnd5e — this seed is "
                    f"the 5e (non-Nimble) authoring."
                )
            return camp["id"]
    # Not found — create it on 5e.
    created = _request(
        "POST", f"{base}/api/v1/campaigns",
        {"name": name, "description": "Curse of Strahd.", "rule_system_id": "dnd5e"},
    )
    assert isinstance(created, dict)
    print(f"created campaign '{name}' ({created['id']})")
    return created["id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="backend base URL")
    parser.add_argument("--campaign", default="Curse of Strahd", help="target campaign name")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    campaign_id = _find_campaign(base, args.campaign)
    root = f"{base}/api/v1/campaigns/{campaign_id}/skill-challenges"

    existing = _request("GET", root)
    assert isinstance(existing, list)
    match = next((c for c in existing if c["name"] == CHALLENGE_NAME), None)

    if match is None:
        result = _request("POST", root, CHALLENGE_BODY)
        assert isinstance(result, dict)
        print(f"created skill challenge '{CHALLENGE_NAME}' ({result['id']})")
    else:
        # PATCH the structured fields; the name lives on the wiki entity and is left as-is.
        result = _request(
            "PATCH", f"{root}/{match['id']}",
            {k: v for k, v in CHALLENGE_BODY.items() if k != "name"},
        )
        assert isinstance(result, dict)
        print(f"updated existing skill challenge '{CHALLENGE_NAME}' ({result['id']})")

    dcs = result["dcs"]
    print(f"  system DCs: easy {dcs['easy']} / normal {dcs['normal']} / hard {dcs['hard']}")
    print(f"  {len(result['approaches'])} approaches, {len(result['outcomes'])} graduated outcomes")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
