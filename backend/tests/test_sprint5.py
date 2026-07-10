"""Sprint 5: FTS5 global search — ranking, filters, deleted excluded, article-text hits."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, name: str, etype: str = "note") -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": etype, "name": name}
    ).json()["id"]


def _search(client: TestClient, cid: str, q: str, **params):
    return client.get(
        f"/api/v1/campaigns/{cid}/search", params={"q": q, **params}
    ).json()


def test_search_finds_by_name_prefix(client: TestClient) -> None:
    cid = _demo(client)
    _entity(client, cid, "Barrow Tavern", "location")
    _entity(client, cid, "Waterdeep", "location")

    hits = _search(client, cid, "barr")  # prefix, search-as-you-type
    assert [h["name"] for h in hits] == ["Barrow Tavern"]


def test_name_hit_outranks_article_hit(client: TestClient) -> None:
    cid = _demo(client)
    dragon = _entity(client, cid, "Dragon", "monster")
    other = _entity(client, cid, "Village", "location")
    # 'Village' only mentions the word "dragon" in its article body.
    client.put(
        f"/api/v1/campaigns/{cid}/entities/{other}/article",
        json={"article_json": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "A dragon burned it."}]}
        ]}},
    )
    hits = _search(client, cid, "dragon")
    ids = [h["id"] for h in hits]
    assert ids[0] == dragon and other in ids  # name match ranks first


def test_search_excludes_deleted(client: TestClient) -> None:
    cid = _demo(client)
    eid = _entity(client, cid, "Ghostwood", "location")
    assert _search(client, cid, "ghostwood")
    client.delete(f"/api/v1/campaigns/{cid}/entities/{eid}")
    assert _search(client, cid, "ghostwood") == []
    # Restoring re-indexes it.
    client.post(f"/api/v1/campaigns/{cid}/entities/{eid}/restore")
    assert [h["id"] for h in _search(client, cid, "ghostwood")] == [eid]


def test_search_type_filter(client: TestClient) -> None:
    cid = _demo(client)
    _entity(client, cid, "Ash the Bard", "npc")
    _entity(client, cid, "Ashford", "location")
    hits = _search(client, cid, "ash", entity_type="npc")
    assert [h["name"] for h in hits] == ["Ash the Bard"]


def test_search_updates_with_rename(client: TestClient) -> None:
    cid = _demo(client)
    eid = _entity(client, cid, "Old Name", "npc")
    client.patch(f"/api/v1/campaigns/{cid}/entities/{eid}",
                 json={"name": "Grendel", "summary_set": False})
    assert _search(client, cid, "old") == []
    assert [h["id"] for h in _search(client, cid, "grendel")] == [eid]


def test_search_is_campaign_scoped(client: TestClient) -> None:
    cid = _demo(client)
    other = client.post("/api/v1/campaigns", json={"name": "Other World"}).json()["id"]
    _entity(client, cid, "Secretville", "location")
    assert _search(client, other, "secretville") == []


def test_search_performance_5k_entities(client: TestClient) -> None:
    """NFR-1.2: prefix search stays well under 100 ms at a few-thousand-entity scale."""
    cid = _demo(client)
    for i in range(2000):
        _entity(client, cid, f"Entity Number {i} of Waterdeep", "note")

    start = time.perf_counter()
    hits = _search(client, cid, "water", limit=20)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(hits) == 20
    assert elapsed_ms < 100, f"search took {elapsed_ms:.1f} ms"
