"""FastAPI application — assembles the modular monolith into one process (ADR-001)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.archive.router import router as archive_router
from app.backup.router import router as backup_router
from app.core import migrations
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.atlas.entity_media_router import router as entity_media_router
from app.modules.atlas.router import router as atlas_router
from app.modules.campaign import service as campaign_service
from app.modules.campaign.router import router as campaign_router
from app.modules.chronicle.router import router as events_router
from app.modules.npcs.router import router as npcs_router
from app.modules.playbook.router import (
    combat_router,
    encounters_router,
    quests_router,
    views_router,
)
from app.modules.playbook.router import router as party_router
from app.modules.rules import bestiary as rules_bestiary
from app.modules.rules import registry as rules_registry
from app.modules.rules.router import blocks_router, monsters_router, systems_router
from app.modules.story.router import router as story_router
from app.modules.time.router import router as time_router
from app.modules.wiki import search as wiki_search
from app.modules.wiki.router import router as entities_router


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject a request whose declared ``Content-Length`` exceeds the configured ceiling,
    before the body is read into memory. Guards the campaign importer (a single JSON body
    with base64 media) and map uploads from exhausting memory (docs/13 §7.9).

    A chunked request without a ``Content-Length`` isn't covered here; the app is
    localhost-bound in the local-first posture, so this ceiling is defense-in-depth for the
    later P-LAN posture rather than a hostile-input boundary.
    """

    def __init__(self, app: object, *, max_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self._max_bytes
        ):
            return JSONResponse(
                {"detail": f"request body exceeds {self._max_bytes} bytes"},
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Apply migrations, then ensure the local user + demo campaign exist (ADR-011).
    migrations.upgrade_to_head()
    with SessionLocal() as session:
        wiki_search.ensure_search_schema(session)
        session.commit()
        rules_registry.sync_rule_systems(session)  # mirror installed plugins into the catalog
        campaign = campaign_service.ensure_bootstrap(session)
        # Seed the demo campaign's bestiary if its system ships content (idempotent).
        if rules_registry.has_system(campaign.rule_system_id):
            rules_bestiary.import_content_packs(session, campaign.id, campaign.rule_system_id)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_bytes)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version", tags=["system"])
    def version() -> dict[str, str]:
        return {"version": app.version}

    app.include_router(campaign_router)
    app.include_router(entities_router)
    app.include_router(events_router)
    app.include_router(time_router)
    app.include_router(systems_router)
    app.include_router(blocks_router)
    app.include_router(monsters_router)
    app.include_router(party_router)
    app.include_router(encounters_router)
    app.include_router(combat_router)
    app.include_router(quests_router)
    app.include_router(views_router)
    app.include_router(npcs_router)
    app.include_router(story_router)
    app.include_router(atlas_router)
    app.include_router(entity_media_router)
    app.include_router(archive_router)
    app.include_router(backup_router)
    return app


app = create_app()
