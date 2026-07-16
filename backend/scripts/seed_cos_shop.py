"""Stock Bildrath's Mercantile (Curse of Strahd) from the equipment library.

Creates the shopkeeper NPC + storefront location + merchant if missing, then adds
a for-sale line for each standard good at its listed shop price. Runs over HTTP
against the live server. Idempotent: existing merchant/goods are reused/skipped.

Usage:  python scripts/seed_cos_shop.py [base_url]
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
CAMPAIGN_NAME = "Curse of Strahd"
SHOP_NAME = "Bildrath's Mercantile"
SHOPKEEPER = "Bildrath"

# (name, listed shop price) — must match names present in the equipment library.
GOODS: list[tuple[str, str]] = [
    ("Abacus", "2 sp"), ("Acid (vial)", "250 gp"), ("Arrows (20)", "10 gp"),
    ("Blowgun Needles (50)", "10 gp"), ("Crossbow Bolts (20)", "10 gp"),
    ("Sling Bullets (20)", "4 sp"), ("Arcane Focus (Crystal)", "100 gp"),
    ("Arcane Focus (Orb)", "200 gp"), ("Arcane Focus (Rod)", "100 gp"),
    ("Arcane Focus (Staff)", "50 gp"), ("Arcane Focus (Wand)", "100 gp"),
    ("Backpack", "20 gp"), ("Ball Bearings (Bag of 1,000)", "10 gp"),
    ("Barrel", "20 gp"), ("Basket", "4 ep"), ("Bedroll", "10 gp"), ("Bell", "10 gp"),
    ("Blanket", "5 ep"), ("Block and Tackle", "10 gp"), ("Book", "250 gp"),
    ("Bottle, Glass", "20 gp"), ("Bucket", "5 sp"), ("Caltrops (Bag of 20)", "10 gp"),
    ("Candle", "1 sp"), ("Case, Crossbow Bolt", "10 gp"), ("Case, Map or Scroll", "10 gp"),
    ("Chain (10 feet)", "50 gp"), ("Chalk (1 piece)", "1 sp"), ("Chest", "50 gp"),
    ("Climber's Kit", "250 gp"), ("Clothes, Common", "5 ep"), ("Clothes, Costume", "50 gp"),
    ("Clothes, Fine", "150 gp"), ("Clothes, Traveler's", "20 gp"), ("Crowbar", "20 gp"),
    ("Druidic Focus (Sprig of Mistletoe)", "10 gp"), ("Druidic Focus (Totem)", "10 gp"),
    ("Druidic Focus (Wooden Staff)", "50 gp"), ("Druidic Focus (Yew Wand)", "100 gp"),
    ("Fishing Tackle", "10 gp"), ("Flask/Tankard", "2 sp"), ("Grappling Hook", "20 gp"),
    ("Hammer", "10 gp"), ("Hammer, Sledge", "20 gp"), ("Healer's Kit", "50 gp"),
    ("Holy Symbol (Amulet)", "50 gp"), ("Holy Symbol (Emblem)", "50 gp"),
    ("Holy Symbol (Reliquary)", "50 gp"), ("Holy Water (Flask)", "250 gp"),
    ("Hourglass", "250 gp"), ("Hunting Trap", "50 gp"), ("Ink (1 ounce bottle)", "100 gp"),
    ("Ink Pen", "2 sp"), ("Jug/Pitcher", "2 sp"), ("Ladder (10-foot)", "1 ep"),
    ("Lantern, Bullseye", "100 gp"), ("Lantern, Hooded", "50 gp"), ("Lock", "100 gp"),
    ("Manacles", "20 gp"), ("Mess Kit", "2 ep"), ("Mirror, Steel", "50 gp"),
    ("Oil (Flask)", "1 ep"), ("Paper (1 sheet)", "2 ep"), ("Parchment (1 sheet)", "1 ep"),
    ("Perfume (Vial)", "50 gp"), ("Pick, Miner's", "20 gp"), ("Piton", "5 sp"),
    ("Pole (10-foot)", "5 sp"), ("Pot, Iron", "20 gp"), ("Pouch", "5 ep"),
    ("Quiver", "10 gp"), ("Ram, Portable", "40 gp"), ("Rations (1 day)", "5 ep"),
    ("Robes", "10 gp"), ("Rope, Hempen (50 feet)", "10 gp"), ("Rope, Silk (50 feet)", "100 gp"),
    ("Sack", "1 sp"), ("Scale, Merchant's", "50 gp"), ("Sealing Wax", "5 ep"),
    ("Shovel", "20 gp"), ("Signal Whistle", "5 sp"), ("Signet Ring", "50 gp"),
    ("Soap", "2 sp"), ("Spikes, Iron (10)", "10 gp"), ("Tent, Two-Person", "20 gp"),
    ("Tinderbox", "5 ep"), ("Torch", "1 sp"), ("Vial", "10 gp"), ("Waterskin", "2 ep"),
    ("Whetstone", "1 sp"),
]


def _get(path: str) -> object:
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _find_or_create_entity(cid: str, entity_type: str, name: str) -> str:
    rows = _get(f"/api/v1/campaigns/{cid}/entities?entity_type={entity_type}")
    match = next((e for e in rows if e["name"] == name), None)
    if match:
        return match["id"]
    return _post(f"/api/v1/campaigns/{cid}/entities",
                 {"entity_type": entity_type, "name": name})["id"]


def main() -> None:
    campaigns = _get("/api/v1/campaigns")
    cos = next((c for c in campaigns if c["name"] == CAMPAIGN_NAME), None)
    if cos is None:
        raise SystemExit(f"campaign {CAMPAIGN_NAME!r} not found")
    cid = cos["id"]

    npc_id = _find_or_create_entity(cid, "npc", SHOPKEEPER)
    loc_id = _find_or_create_entity(cid, "location", SHOP_NAME)

    merchants = _get(f"/api/v1/campaigns/{cid}/merchants")
    shop = next((m for m in merchants if m["name"] == SHOP_NAME), None)
    if shop is None:
        shop = _post(f"/api/v1/campaigns/{cid}/merchants", {
            "name": SHOP_NAME,
            "summary": "The general store of the Village of Barovia (E1). Bildrath charges a steep markup — there's nowhere else to shop.",
            "npc_id": npc_id, "location_id": loc_id, "buyback_pct": 25,
        })
        print(f"created merchant {SHOP_NAME}")
    mid = shop["entity_id"]

    library = {e["name"]: e["id"] for e in _get("/api/v1/equipment-library")}
    stocked = {s["name"] for s in _get(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock")}

    added = skipped = missing = 0
    for name, price in GOODS:
        if name in stocked:
            skipped += 1
            continue
        lib_id = library.get(name)
        if not lib_id:
            print(f"  ! not in library: {name}")
            missing += 1
            continue
        _post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
              {"library_id": lib_id, "price": price})
        added += 1

    print(f"\nDone: {added} stocked, {skipped} already present, {missing} missing from library.")


if __name__ == "__main__":
    main()
