"""Sprint 3: @mentions in articles create/remove bidirectional links; plaintext extracted."""

from __future__ import annotations

from app.modules.wiki.article import extract_mention_ids, extract_plain_text
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _new_entity(client: TestClient, cid: str, name: str, etype: str = "note") -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": etype, "name": name}
    ).json()["id"]


def _doc_mentioning(target_id: str, label: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "The party met "},
                    {"type": "mention", "attrs": {"id": target_id, "label": label}},
                    {"type": "text", "text": " at the tavern."},
                ],
            }
        ],
    }


# --- pure extraction --------------------------------------------------------
def test_extract_mentions_and_plaintext() -> None:
    doc = _doc_mentioning("abc", "Serah Voss")
    assert extract_mention_ids(doc) == ["abc"]
    assert extract_plain_text(doc) == "The party met @Serah Voss at the tavern."


def test_extract_dedupes_mentions() -> None:
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "mention", "attrs": {"id": "x"}}]},
            {"type": "paragraph", "content": [{"type": "mention", "attrs": {"id": "x"}}]},
        ],
    }
    assert extract_mention_ids(doc) == ["x"]


# --- mention -> link diff sync (the exit criterion) -------------------------
def test_mention_creates_and_removes_link_with_backlink(client: TestClient) -> None:
    cid = _demo(client)
    author = _new_entity(client, cid, "Chapter 1", "note")
    tavern = _new_entity(client, cid, "Barrow Tavern", "location")

    # Save an article that @mentions the tavern → outbound link + backlink appear.
    detail = client.put(
        f"/api/v1/campaigns/{cid}/entities/{author}/article",
        json={"article_json": _doc_mentioning(tavern, "Barrow Tavern")},
    ).json()
    assert [o["entity_id"] for o in detail["outbound"]] == [tavern]
    assert detail["outbound"][0]["link_type"] == "mentions"

    # The tavern automatically lists the author as a backlink (FR-2.3).
    tavern_detail = client.get(f"/api/v1/campaigns/{cid}/entities/{tavern}").json()
    assert [b["entity_id"] for b in tavern_detail["backlinks"]] == [author]
    assert tavern_detail["backlinks"][0]["label"] == "mentioned by"

    # Remove the mention (empty doc) → link and backlink disappear.
    empty = client.put(
        f"/api/v1/campaigns/{cid}/entities/{author}/article",
        json={"article_json": {"type": "doc", "content": []}},
    ).json()
    assert empty["outbound"] == []
    tavern_detail = client.get(f"/api/v1/campaigns/{cid}/entities/{tavern}").json()
    assert tavern_detail["backlinks"] == []

    # Both directions were audited.
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "link_added" in types and "link_removed" in types


def test_mentions_are_deduped_and_ignore_bad_ids(client: TestClient) -> None:
    cid = _demo(client)
    author = _new_entity(client, cid, "Notes", "note")
    real = _new_entity(client, cid, "Real NPC", "npc")

    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [
                {"type": "mention", "attrs": {"id": real, "label": "Real NPC"}},
                {"type": "mention", "attrs": {"id": real, "label": "Real NPC"}},
                {"type": "mention", "attrs": {"id": "does-not-exist", "label": "Ghost"}},
            ]},
        ],
    }
    detail = client.put(
        f"/api/v1/campaigns/{cid}/entities/{author}/article", json={"article_json": doc}
    ).json()
    # Deduped to one, bogus id dropped.
    assert [o["entity_id"] for o in detail["outbound"]] == [real]


def test_entity_search_for_autocomplete(client: TestClient) -> None:
    cid = _demo(client)
    _new_entity(client, cid, "Barrow Tavern", "location")
    _new_entity(client, cid, "Barrowmaze", "location")
    _new_entity(client, cid, "Waterdeep", "location")

    hits = client.get(f"/api/v1/campaigns/{cid}/entities", params={"q": "barrow"}).json()
    names = sorted(e["name"] for e in hits)
    assert names == ["Barrow Tavern", "Barrowmaze"]
