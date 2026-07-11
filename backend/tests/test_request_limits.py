"""The request-size ceiling (docs/13 §7.9): oversized bodies are rejected before parsing.

Built against a throwaway app with a tiny limit so the real middleware is exercised without
sending hundreds of megabytes.
"""

from __future__ import annotations

from typing import Any

from app.main import MaxBodySizeMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(max_bytes: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    def echo(body: dict[str, Any]) -> dict[str, Any]:
        return body

    return app


def test_oversized_body_is_rejected_with_413() -> None:
    client = TestClient(_app(max_bytes=50))
    resp = client.post("/echo", json={"blob": "x" * 500})
    assert resp.status_code == 413
    assert "exceeds" in resp.text.lower()


def test_body_within_limit_passes_through() -> None:
    client = TestClient(_app(max_bytes=10_000))
    resp = client.post("/echo", json={"ok": True})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
