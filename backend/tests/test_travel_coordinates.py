import struct
import zlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, entity_type: str, name: str) -> str:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": entity_type, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _png(width: int, height: int) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def _tmp_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _upload(client: TestClient, cid: str, name: str) -> dict:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps",
        data={"name": name, "map_kind": "world"},
        files={"file": (f"{name}.png", _png(400, 300), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_party_position_patch_and_travel_snapping(client: TestClient) -> None:
    cid = _demo(client)
    
    # 1. Update party coordinates manually via patch endpoint
    party = client.patch(
        f"/api/v1/campaigns/{cid}/party",
        json={"current_x": 150.0, "current_y": 250.0, "coordinates_set": True}
    ).json()
    assert party["current_x"] == 150.0
    assert party["current_y"] == 250.0
    
    # 2. Upload a map and link a marker to a location
    map_detail = _upload(client, cid, "Barovia")
    map_id = map_detail["entity_id"]
    
    loc_id = _entity(client, cid, "location", "Castle Ravenloft")
    
    # Create marker at (100, 200) linking to location "Castle Ravenloft"
    resp = client.post(
        f"/api/v1/campaigns/{cid}/maps/{map_id}/markers",
        json={"x": 100.0, "y": 200.0, "target_entity_id": loc_id, "layer": "default"}
    )
    assert resp.status_code == 201, resp.text
    
    # Update party location to start somewhere else
    client.patch(
        f"/api/v1/campaigns/{cid}/party",
        json={"current_location_id": None, "location_set": True}
    )
    
    # 3. Commit travel to Castle Ravenloft
    body = {"legs": [{"distance": 5, "terrain": "road", "to_location_id": loc_id}]}
    res = client.post(f"/api/v1/campaigns/{cid}/party/travel", json=body).json()
    assert res["destination_id"] == loc_id
    
    # 4. Verify party has snapped to the location marker's coordinates and map
    party = client.get(f"/api/v1/campaigns/{cid}/party").json()
    assert party["current_location_id"] == loc_id
    assert party["current_map_id"] == map_id
    assert party["current_x"] == 100.0
    assert party["current_y"] == 200.0

    # 5. Travel to an unmapped location
    unmapped_loc_id = _entity(client, cid, "location", "Nowhere Town")
    body2 = {"legs": [{"distance": 10, "terrain": "road", "to_location_id": unmapped_loc_id}]}
    client.post(f"/api/v1/campaigns/{cid}/party/travel", json=body2)
    
    # Verify coordinates are cleared
    party = client.get(f"/api/v1/campaigns/{cid}/party").json()
    assert party["current_location_id"] == unmapped_loc_id
    assert party["current_map_id"] is None
    assert party["current_x"] is None
    assert party["current_y"] is None


def test_map_scale_calibration_persists(client: TestClient) -> None:
    cid = _demo(client)
    map_detail = _upload(client, cid, "Waterdeep")
    map_id = map_detail["entity_id"]

    # Calibration setting should be None initially
    assert map_detail.get("scale_pixels_per_unit") is None
    assert map_detail.get("scale_unit") == "mile"

    # Calibrate map scale via PATCH
    updated = client.patch(
        f"/api/v1/campaigns/{cid}/maps/{map_id}",
        json={"scale_pixels_per_unit": 50.0, "scale_unit": "mile", "scale_set": True}
    ).json()
    assert updated["scale_pixels_per_unit"] == 50.0
    assert updated["scale_unit"] == "mile"

    # Verify that reloading the map returns the correct scale settings
    reloaded = client.get(f"/api/v1/campaigns/{cid}/maps/{map_id}").json()
    assert reloaded["scale_pixels_per_unit"] == 50.0
    assert reloaded["scale_unit"] == "mile"
