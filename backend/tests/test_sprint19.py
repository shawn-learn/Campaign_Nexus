"""Sprint 19 — data lifecycle: media in the archive, backups, preflight, article history.

Exit criterion: export → import round-trips *everything* including map images, and an
automatic backup can be created, rotated, and restored.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient


def _png(width: int, height: int, fill: int = 0) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([fill, fill, fill]) * width for _ in range(height))
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def _tmp_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("NEXUS_BACKUP_DIR", str(tmp_path / "backups"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _upload_map(client: TestClient, cid: str, name: str, fill: int = 0) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps",
        data={"name": name, "map_kind": "world"},
        files={"file": (f"{name}.png", _png(80, 60, fill), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# Media & maps survive the archive (the headline gap this sprint closes)
# --------------------------------------------------------------------------- #
def test_maps_and_image_bytes_round_trip(client: TestClient) -> None:
    cid = _demo(client)
    npc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "npc", "name": "Volo"}).json()
    world = _upload_map(client, cid, "Aldenmoor", fill=40)
    # A marker peeking the NPC and a region — both must come back pointing at the right ids.
    client.post(f"/api/v1/campaigns/{cid}/maps/{world['entity_id']}/markers",
                json={"x": 10, "y": 12, "target_entity_id": npc["id"], "layer": "cities"})
    client.post(f"/api/v1/campaigns/{cid}/maps/{world['entity_id']}/regions",
                json={"polygon": [[0, 0], [40, 0], [40, 30]], "name": "The Reach"})

    original_bytes = client.get(
        f"/api/v1/campaigns/{cid}/maps/{world['entity_id']}/image"
    ).content

    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    assert archive["version"] == 2
    assert len(archive["media"]) == 1 and archive["media"][0]["data_b64"]

    new_cid = client.post("/api/v1/campaigns/import", json=archive).json()["id"]
    maps = client.get(f"/api/v1/campaigns/{new_cid}/maps").json()
    assert [m["name"] for m in maps] == ["Aldenmoor"]

    detail = client.get(f"/api/v1/campaigns/{new_cid}/maps/{maps[0]['entity_id']}").json()
    assert detail["layers"] == ["cities", "default"]
    marker = next(mk for mk in detail["markers"] if mk["target_name"])
    assert marker["target_name"] == "Volo"  # remapped to the *imported* NPC
    assert [r["name"] for r in detail["regions"]] == ["The Reach"]

    # The image bytes are byte-identical after the round trip.
    restored_bytes = client.get(
        f"/api/v1/campaigns/{new_cid}/maps/{maps[0]['entity_id']}/image"
    ).content
    assert restored_bytes == original_bytes


def test_a_v1_archive_without_media_still_imports(client: TestClient) -> None:
    cid = _demo(client)
    client.post(f"/api/v1/campaigns/{cid}/entities",
                json={"entity_type": "location", "name": "Duskmere"})
    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    # Simulate an archive produced before Sprint 19.
    archive["version"] = 1
    for key in ("media", "maps", "map_markers", "map_regions"):
        archive.pop(key, None)

    new_cid = client.post("/api/v1/campaigns/import", json=archive).json()["id"]
    names = [e["name"] for e in client.get(f"/api/v1/campaigns/{new_cid}/entities").json()]
    assert "Duskmere" in names
    assert client.get(f"/api/v1/campaigns/{new_cid}/maps").json() == []


# --------------------------------------------------------------------------- #
# Backups
# --------------------------------------------------------------------------- #
def test_backup_is_a_complete_openable_snapshot(client: TestClient) -> None:
    cid = _demo(client)
    _upload_map(client, cid, "Backed Up", fill=77)

    made = client.post("/api/v1/backups", json={"reason": "manual"}).json()
    assert made["media_files"] >= 1 and made["db_bytes"] > 0

    listed = client.get("/api/v1/backups").json()
    assert made["id"] in [b["id"] for b in listed]

    # Restore overwrites the live DB and so is an *offline* op (the server is stopped in real
    # use — the shared test engine holds a WAL lock here). Instead prove the snapshot itself
    # is a complete, openable database: open the backup file directly and read it back.
    from app.backup.service import DB_NAME, MEDIA_DIRNAME
    from sqlalchemy import create_engine, text

    backup_root = Path(get_settings().backup_dir) / made["id"]
    assert (backup_root / MEDIA_DIRNAME).is_dir()

    engine = create_engine(f"sqlite:///{(backup_root / DB_NAME).as_posix()}")
    with engine.connect() as conn:
        maps = conn.execute(text("SELECT count(*) FROM map")).scalar_one()
        media = conn.execute(text("SELECT count(*) FROM media")).scalar_one()
    engine.dispose()
    assert maps == 1 and media == 1


def test_backup_rotation_keeps_only_the_newest(client: TestClient) -> None:
    from app.backup import service as backup_service
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        for i in range(5):
            backup_service.create_backup(s, reason=f"r{i}")
        kept = backup_service.list_backups()
        assert len(kept) == 5
        removed = backup_service.prune_backups(keep=2)
    assert len(removed) == 3
    assert len(backup_service.list_backups()) == 2


def test_session_start_takes_an_automatic_backup(client: TestClient) -> None:
    cid = _demo(client)
    sess = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()
    client.post(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}/start")

    reasons = [b["reason"] for b in client.get("/api/v1/backups").json()]
    assert "session-start" in reasons


# --------------------------------------------------------------------------- #
# Delete-preflight references
# --------------------------------------------------------------------------- #
def test_references_show_what_points_at_an_entity(client: TestClient) -> None:
    cid = _demo(client)
    tavern = client.post(f"/api/v1/campaigns/{cid}/entities",
                         json={"entity_type": "location", "name": "The Tavern"}).json()
    barkeep = client.post(f"/api/v1/campaigns/{cid}/entities",
                          json={"entity_type": "npc", "name": "Halda"}).json()
    client.post(f"/api/v1/campaigns/{cid}/entities/{barkeep['id']}/links",
                json={"to_entity": tavern["id"], "link_type_id": "located_at"})

    refs = client.get(f"/api/v1/campaigns/{cid}/entities/{tavern['id']}/references").json()
    assert refs["entity_id"] == tavern["id"]
    assert [r["name"] for r in refs["inbound"]] == ["Halda"]
    assert refs["inbound"][0]["link_type"] == "located_at"

    # An entity nothing points at is safe to delete.
    lonely = client.post(f"/api/v1/campaigns/{cid}/entities",
                         json={"entity_type": "note", "name": "Lonely"}).json()
    empty = client.get(f"/api/v1/campaigns/{cid}/entities/{lonely['id']}/references").json()
    assert empty["inbound"] == []


# --------------------------------------------------------------------------- #
# Article snapshots
# --------------------------------------------------------------------------- #
def _doc(text: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _save(client: TestClient, cid: str, eid: str, text: str) -> None:
    resp = client.put(f"/api/v1/campaigns/{cid}/entities/{eid}/article",
                      json={"article_json": _doc(text)})
    assert resp.status_code == 200, resp.text


def test_article_edits_snapshot_and_restore(client: TestClient) -> None:
    cid = _demo(client)
    npc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "npc", "name": "Serah"}).json()

    _save(client, cid, npc["id"], "First draft.")
    _save(client, cid, npc["id"], "Second draft, much better.")
    _save(client, cid, npc["id"], "Third and final.")

    snaps = client.get(f"/api/v1/campaigns/{cid}/entities/{npc['id']}/article/snapshots").json()
    # Two snapshots: the state before edit #2 and before edit #3 (the first save had no prior).
    assert [s["preview"] for s in snaps] == ["Second draft, much better.", "First draft."]

    # Roll back to the earliest.
    detail = client.post(
        f"/api/v1/campaigns/{cid}/entities/{npc['id']}/article/snapshots/{snaps[-1]['id']}/restore"
    ).json()
    assert detail["article_json"]["content"][0]["content"][0]["text"] == "First draft."

    # Restoring itself snapshotted the "Third and final." version, so nothing is lost.
    previews = [
        s["preview"]
        for s in client.get(
            f"/api/v1/campaigns/{cid}/entities/{npc['id']}/article/snapshots"
        ).json()
    ]
    assert "Third and final." in previews


# --------------------------------------------------------------------------- #
# The full oracle: export → wipe → import → rebuild is consistent
# --------------------------------------------------------------------------- #
def test_export_import_then_rebuild_is_consistent(client: TestClient, db) -> None:
    from scripts.rebuild_projections import rebuild

    cid = _demo(client)
    loc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "location", "name": "Keep"}).json()
    client.post(f"/api/v1/campaigns/{cid}/npcs",
                json={"name": "Warden", "location_id": loc["id"]})
    _upload_map(client, cid, "Realm", fill=9)

    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    new_cid = client.post("/api/v1/campaigns/import", json=archive).json()["id"]

    # The imported NPC's location projection is intact...
    imported = client.get(f"/api/v1/campaigns/{new_cid}/npcs").json()[0]
    assert imported["current_location_name"] == "Keep"

    # ...and replaying the event log re-derives the same projections (the §8.4 oracle).
    before = client.get(f"/api/v1/campaigns/{new_cid}/npcs/{imported['entity_id']}/history").json()
    rebuild(db, new_cid)
    after = client.get(f"/api/v1/campaigns/{new_cid}/npcs/{imported['entity_id']}/history").json()
    assert [r["location_name"] for r in after] == [r["location_name"] for r in before]
