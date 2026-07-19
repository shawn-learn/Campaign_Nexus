from __future__ import annotations

from app.modules.merchant.money import cp_to_gp_ceil, format_cp, parse_cp
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, entity_type: str, name: str) -> str:
    r = client.post(f"/api/v1/campaigns/{cid}/entities",
                    json={"entity_type": entity_type, "name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _lib_entry(client: TestClient, name: str, value_gp: str) -> str:
    r = client.post("/api/v1/equipment-library",
                    json={"name": name, "item_type": "mundane", "value_gp": value_gp})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set_gold(client: TestClient, cid: str, gold: int) -> None:
    assert client.patch(f"/api/v1/campaigns/{cid}/party", json={"gold": gold}).status_code == 200


def _gold(client: TestClient, cid: str) -> int:
    return client.get(f"/api/v1/campaigns/{cid}/party").json()["gold"]


# -- money --------------------------------------------------------------------

def test_money_parsing_and_formatting() -> None:
    assert parse_cp("2 sp") == 20
    assert parse_cp("5 ep") == 250
    assert parse_cp("250 gp") == 25000
    assert parse_cp("1 cp") == 1
    assert parse_cp("nonsense") is None
    assert cp_to_gp_ceil(20) == 1        # 2 sp rounds up to 1 gp
    assert cp_to_gp_ceil(1500) == 15
    assert format_cp(250) == "5 ep"
    assert format_cp(1500) == "15 gp"


# -- merchant CRUD ------------------------------------------------------------

def test_merchant_crud_with_links(client: TestClient) -> None:
    cid = _demo(client)
    npc = _entity(client, cid, "npc", "Bildrath")
    loc = _entity(client, cid, "location", "Bildrath's Mercantile")

    made = client.post(f"/api/v1/campaigns/{cid}/merchants",
                       json={"name": "Bildrath's Mercantile", "npc_id": npc,
                             "location_id": loc, "buyback_pct": 25})
    assert made.status_code == 201, made.text
    m = made.json()
    assert m["npc_name"] == "Bildrath"
    assert m["location_name"] == "Bildrath's Mercantile"
    assert m["buyback_pct"] == 25
    assert m["stock_count"] == 0

    listed = client.get(f"/api/v1/campaigns/{cid}/merchants").json()
    assert any(x["entity_id"] == m["entity_id"] for x in listed)

    # Unlink the NPC via the clear flag.
    patched = client.patch(f"/api/v1/campaigns/{cid}/merchants/{m['entity_id']}",
                           json={"clear_npc": True}).json()
    assert patched["npc_id"] is None


def _merchant(client: TestClient, cid: str) -> str:
    return client.post(f"/api/v1/campaigns/{cid}/merchants",
                       json={"name": "General Store"}).json()["entity_id"]


def test_stock_add_price_from_string_and_default(client: TestClient) -> None:
    cid = _demo(client)
    mid = _merchant(client, cid)
    torch = _lib_entry(client, "Torch (shop)", "1 sp")

    # Explicit price string overrides the template value.
    line = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                       json={"library_id": torch, "price": "20 gp", "quantity": 5}).json()
    assert line["price_cp"] == 2000
    assert line["price_label"] == "20 gp"
    assert line["quantity"] == 5

    # No price given -> falls back to the template's value_gp ("1 sp" = 10 cp).
    line2 = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                        json={"library_id": torch}).json()
    assert line2["price_cp"] == 10


def test_purchase_deducts_gold_and_hands_over_item(client: TestClient) -> None:
    cid = _demo(client)
    mid = _merchant(client, cid)
    lib = _lib_entry(client, "Adventuring Kit", "15 gp")
    line = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                       json={"library_id": lib, "price": "15 gp", "quantity": 3}).json()
    _set_gold(client, cid, 100)

    bought = client.post(
        f"/api/v1/campaigns/{cid}/merchants/{mid}/stock/{line['id']}/buy",
        json={"quantity": 2},
    )
    assert bought.status_code == 200, bought.text
    res = bought.json()
    assert len(res["item_ids"]) == 2
    assert res["total_cp"] == 3000
    assert res["party_gold"] == 70  # 100 - 30
    assert _gold(client, cid) == 70

    # Stock decremented, and the party now holds two copies.
    remaining = client.get(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock").json()
    assert remaining[0]["quantity"] == 1
    party_items = client.get(f"/api/v1/campaigns/{cid}/items", params={"holder_type": "party"}).json()
    assert sum(1 for i in party_items if i["equipment_name"] == "Adventuring Kit") == 2


def test_purchase_rejects_insufficient_gold_and_overstock(client: TestClient) -> None:
    cid = _demo(client)
    mid = _merchant(client, cid)
    lib = _lib_entry(client, "Pricey Thing", "500 gp")
    line = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                       json={"library_id": lib, "price": "500 gp", "quantity": 1}).json()
    _set_gold(client, cid, 100)

    poor = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock/{line['id']}/buy",
                       json={"quantity": 1})
    assert poor.status_code == 422
    assert "afford" in poor.json()["detail"]
    assert _gold(client, cid) == 100  # unchanged

    _set_gold(client, cid, 10000)
    over = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock/{line['id']}/buy",
                       json={"quantity": 5})
    assert over.status_code == 422
    assert "stock" in over.json()["detail"]


def _party(client: TestClient, cid: str) -> dict:
    return client.get(f"/api/v1/campaigns/{cid}/party").json()


def test_wealth_tracks_copper_exactly(client: TestClient) -> None:
    cid = _demo(client)
    mid = _merchant(client, cid)
    abacus = _lib_entry(client, "Abacus (shop)", "2 sp")  # 20 cp
    line = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                       json={"library_id": abacus, "price": "2 sp"}).json()

    # Start with exactly 1 gp = 100 cp.
    client.patch(f"/api/v1/campaigns/{cid}/party", json={"wealth_cp": 100})
    party = _party(client, cid)
    assert party["wealth_cp"] == 100
    assert party["wealth_label"] == "1 gp"

    bought = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock/{line['id']}/buy",
                         json={"quantity": 1}).json()
    # 2 sp deducted exactly — no rounding up to a whole gp.
    assert bought["party_wealth_cp"] == 80
    assert bought["party_wealth_label"] == "8 sp"
    assert _party(client, cid)["wealth_cp"] == 80


def test_sellback_credits_gold_and_removes_item(client: TestClient) -> None:
    cid = _demo(client)
    mid = client.post(f"/api/v1/campaigns/{cid}/merchants",
                      json={"name": "Pawnshop", "buyback_pct": 50}).json()["entity_id"]
    lib = _lib_entry(client, "Silver Ring", "20 gp")
    line = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock",
                       json={"library_id": lib, "price": "20 gp"}).json()
    _set_gold(client, cid, 0)

    _set_gold(client, cid, 100)
    bought = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/stock/{line['id']}/buy",
                         json={"quantity": 1}).json()
    item_id = bought["item_ids"][0]
    assert _gold(client, cid) == 80

    sold = client.post(f"/api/v1/campaigns/{cid}/merchants/{mid}/sell",
                       json={"item_id": item_id})
    assert sold.status_code == 200, sold.text
    # 20 gp value * 50% = 10 gp credited.
    assert sold.json()["credited_gp"] == 10
    assert _gold(client, cid) == 90
    # The copy is gone.
    assert client.get(f"/api/v1/campaigns/{cid}/items/{item_id}").status_code == 404
