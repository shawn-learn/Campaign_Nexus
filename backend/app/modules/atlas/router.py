from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.atlas import imagesize, service
from app.modules.atlas.schemas import (
    MapDetail,
    MapSummary,
    MapUpdate,
    MarkerCreate,
    MarkerOut,
    MarkerUpdate,
    RegionCreate,
    RegionOut,
    RegionUpdate,
)
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/maps", tags=["atlas"])

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))

_MAX_BYTES = 32 * 1024 * 1024  # 32 MB — generous for a battle/region map, bounds abuse


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:  # pragma: no cover - scope guard already ran
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


@router.get("", response_model=list[MapSummary])
def list_maps(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> list[MapSummary]:
    return service.list_maps(session, ctx.campaign_id)


@router.post("", response_model=MapDetail, status_code=status.HTTP_201_CREATED)
async def upload_map(
    file: UploadFile = File(...),
    name: str = Form(...),
    map_kind: str = Form("region"),
    location_id: str | None = Form(None),
    parent_map_id: str | None = Form(None),
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> MapDetail:
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image too large (max 32 MB)")
    try:
        imagesize.sniff(data)  # validate before touching disk
        return service.upload_map(
            session, _campaign(session, ctx.campaign_id),
            name=name, data=data, filename=file.filename or "map",
            map_kind=map_kind, location_id=location_id or None,
            parent_map_id=parent_map_id or None, created_by=ctx.user_id,
        )
    except imagesize.BadImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except service.AtlasError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/{map_id}", response_model=MapDetail)
def get_map(
    map_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> MapDetail:
    try:
        return service.get_map(session, ctx.campaign_id, map_id)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc


@router.get("/{map_id}/image")
def get_map_image(
    map_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Viewer
) -> FileResponse:
    try:
        media = service.media_for_map(session, ctx.campaign_id, map_id)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc
    path = service.media_abspath(media)
    if not path.exists():  # pragma: no cover - disk/db drift
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image file missing")
    # Content-addressed name → safe to cache aggressively.
    return FileResponse(
        path, media_type=media.mime,
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )


@router.patch("/{map_id}", response_model=MapDetail)
def update_map(
    map_id: str,
    body: MapUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> MapDetail:
    try:
        return service.update_map(
            session, ctx.campaign_id, map_id,
            name=body.name, map_kind=body.map_kind,
            location_id=body.location_id, parent_map_id=body.parent_map_id,
        )
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map(
    map_id: str, session: Session = Depends(get_session), ctx: CampaignContext = Editor
) -> None:
    try:
        service.delete_map(session, ctx.campaign_id, map_id)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #
@router.post("/{map_id}/markers", response_model=MarkerOut, status_code=status.HTTP_201_CREATED)
def add_marker(
    map_id: str,
    body: MarkerCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> MarkerOut:
    try:
        return service.add_marker(session, ctx.campaign_id, map_id, body)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc
    except service.AtlasError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/{map_id}/markers/{marker_id}", response_model=MarkerOut)
def update_marker(
    map_id: str,
    marker_id: str,
    body: MarkerUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> MarkerOut:
    try:
        return service.update_marker(session, ctx.campaign_id, map_id, marker_id, body)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "marker not found") from exc
    except service.AtlasError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete("/{map_id}/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marker(
    map_id: str,
    marker_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_marker(session, ctx.campaign_id, map_id, marker_id)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "marker not found") from exc


# --------------------------------------------------------------------------- #
# Regions (polygons)
# --------------------------------------------------------------------------- #
@router.post("/{map_id}/regions", response_model=RegionOut, status_code=status.HTTP_201_CREATED)
def add_region(
    map_id: str,
    body: RegionCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> RegionOut:
    try:
        return service.add_region(session, ctx.campaign_id, map_id, body)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "map not found") from exc
    except service.AtlasError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/{map_id}/regions/{region_id}", response_model=RegionOut)
def update_region(
    map_id: str,
    region_id: str,
    body: RegionUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> RegionOut:
    try:
        return service.update_region(session, ctx.campaign_id, map_id, region_id, body)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "region not found") from exc
    except service.AtlasError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete("/{map_id}/regions/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region(
    map_id: str,
    region_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_region(session, ctx.campaign_id, map_id, region_id)
    except service.MapNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "region not found") from exc
