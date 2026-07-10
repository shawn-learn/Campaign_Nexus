"""Sprint 15 — the Atlas: map upload, entity-linked markers, child-map drill-down (FR-3)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient


def _png(width: int, height: int) -> bytes:
    """A minimal but valid RGB PNG of the given size (only the IHDR dims matter to us)."""
    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def _tmp_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _upload(
    client: TestClient, cid: str, name: str, w: int = 400, h: int = 300, **form: str
) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps",
        data={"name": name, **form},
        files={"file": (f"{name}.png", _png(w, h), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_reads_dimensions_and_lists(client: TestClient) -> None:
    cid = _demo(client)
    detail = _upload(client, cid, "Faerûn", 1024, 768, map_kind="world")
    assert detail["width_px"] == 1024
    assert detail["height_px"] == 768
    assert detail["map_kind"] == "world"

    # The map is a real wiki entity (in the graph + search).
    hits = client.get(f"/api/v1/campaigns/{cid}/search", params={"q": "Faerûn"}).json()
    assert any(h["name"] == "Faerûn" for h in hits)

    maps = client.get(f"/api/v1/campaigns/{cid}/maps").json()
    assert any(m["entity_id"] == detail["entity_id"] and m["marker_count"] == 0 for m in maps)

    # The image is served back with the right bytes.
    img = client.get(f"/api/v1/campaigns/{cid}/maps/{detail['entity_id']}/image")
    assert img.status_code == 200
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_rejects_non_image(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps",
        data={"name": "Bogus"},
        files={"file": ("notes.txt", b"just text, not an image", "text/plain")},
    )
    assert resp.status_code == 422


def test_marker_targets_entity_for_peek(client: TestClient) -> None:
    cid = _demo(client)
    world = _upload(client, cid, "Overworld")["entity_id"]
    npc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "npc", "name": "Elowen"}).json()["id"]

    marker = client.post(
        f"/api/v1/campaigns/{cid}/maps/{world}/markers",
        json={"x": 120.5, "y": 88.0, "target_entity_id": npc, "note": "the seer"},
    )
    assert marker.status_code == 201, marker.text
    body = marker.json()
    assert body["target_name"] == "Elowen"
    assert body["target_type"] == "npc"

    detail = client.get(f"/api/v1/campaigns/{cid}/maps/{world}").json()
    assert len(detail["markers"]) == 1
    assert detail["markers"][0]["x"] == 120.5


def test_child_map_drill_down(client: TestClient) -> None:
    cid = _demo(client)
    world = _upload(client, cid, "World", 2000, 2000, map_kind="world")["entity_id"]
    city = _upload(client, cid, "Waterdeep", 1000, 1000, map_kind="city",
                   parent_map_id=world)["entity_id"]

    # A marker on the world map that drills into the city map.
    client.post(
        f"/api/v1/campaigns/{cid}/maps/{world}/markers",
        json={"x": 50, "y": 60, "child_map_id": city},
    )
    detail = client.get(f"/api/v1/campaigns/{cid}/maps/{world}").json()
    m = detail["markers"][0]
    assert m["child_map_id"] == city
    assert m["child_map_name"] == "Waterdeep"

    # The city map knows its parent (for the breadcrumb stack).
    city_detail = client.get(f"/api/v1/campaigns/{cid}/maps/{city}").json()
    assert city_detail["parent_map_id"] == world
    assert city_detail["parent_map_name"] == "World"


def test_marker_target_must_exist(client: TestClient) -> None:
    cid = _demo(client)
    world = _upload(client, cid, "Nowhere")["entity_id"]
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps/{world}/markers",
        json={"x": 1, "y": 1, "target_entity_id": "no-such-entity"},
    )
    assert resp.status_code == 422


def test_delete_map_removes_markers(client: TestClient) -> None:
    cid = _demo(client)
    world = _upload(client, cid, "Doomed")["entity_id"]
    client.post(f"/api/v1/campaigns/{cid}/maps/{world}/markers", json={"x": 1, "y": 2})
    assert client.delete(f"/api/v1/campaigns/{cid}/maps/{world}").status_code == 204
    assert client.get(f"/api/v1/campaigns/{cid}/maps/{world}").status_code == 404
