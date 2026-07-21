from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.wiki import service
from app.modules.wiki.schemas import (
    ArticleSnapshotOut,
    ArticleUpdate,
    EntityCreate,
    EntityDetail,
    EntityOut,
    EntityUpdate,
    LinkCreate,
    LinkTypeCreate,
    LinkTypeOut,
    PurgedEntity,
    PurgeResult,
    ReferencesOut,
    SearchHitOut,
    TagCreate,
    TagOut,
)

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}", tags=["wiki"])

# Reusable scope guards (NFR-6.2): reads need viewer, writes need editor.
Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "entity not found")


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
@router.get("/entities", response_model=list[EntityOut])
def get_entities(
    entity_type: str | None = None,
    tag_id: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    sort: str | None = None,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[EntityOut]:
    entities = service.list_entities(
        session, ctx.campaign_id,
        entity_type=entity_type, tag_id=tag_id, q=q,
        include_deleted=include_deleted, sort=sort,
    )
    return [service.to_out(session, e) for e in entities]


@router.get("/search", response_model=list[EntityOut])
def search_entities(
    q: str,
    entity_type: str | None = None,
    tag_id: str | None = None,
    limit: int = 20,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[EntityOut]:
    hits = service.full_text_search(
        session, ctx.campaign_id, q,
        entity_type=entity_type, tag_id=tag_id, limit=min(limit, 50),
    )
    return [service.to_out(session, e) for e in hits]


@router.get("/search/deep", response_model=list[SearchHitOut])
def search_entities_deep(
    q: str,
    entity_type: str | None = None,
    tag_id: str | None = None,
    prose_only: bool = False,
    limit: int = 25,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[SearchHitOut]:
    """Ranked search with highlighted snippets of the summary/article text that matched.

    ``prose_only`` ignores name and tag matches, answering "where did I write about this?"
    """
    return service.deep_search(
        session, ctx.campaign_id, q,
        entity_type=entity_type, tag_id=tag_id,
        prose_only=prose_only, limit=min(limit, 100),
    )


@router.post("/entities", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
def post_entity(
    body: EntityCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.create_entity(
            session, ctx.campaign_id, data=body, created_by=ctx.user_id
        )
    except service.UnknownEntityType as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown entity_type: {exc}"
        ) from exc
    return service.to_out(session, entity)


@router.get("/entities/{entity_id}", response_model=EntityDetail)
def get_entity(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> EntityDetail:
    try:
        entity = service.get_entity(session, ctx.campaign_id, entity_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return service.to_detail(session, entity)


@router.put("/entities/{entity_id}/article", response_model=EntityDetail)
def put_article(
    entity_id: str,
    body: ArticleUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityDetail:
    try:
        entity = service.update_article(
            session, ctx.campaign_id, entity_id, article_json=body.article_json
        )
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return service.to_detail(session, entity)


@router.get("/entities/{entity_id}/references", response_model=ReferencesOut)
def get_references(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> ReferencesOut:
    """What points at this entity — shown before a delete so nothing is severed blindly."""
    try:
        inbound = service.references_to(session, ctx.campaign_id, entity_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return ReferencesOut(entity_id=entity_id, inbound=inbound)


@router.get("/entities/{entity_id}/article/snapshots", response_model=list[ArticleSnapshotOut])
def list_article_snapshots(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[ArticleSnapshotOut]:
    try:
        rows = service.list_article_snapshots(session, ctx.campaign_id, entity_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return [ArticleSnapshotOut.model_validate(r) for r in rows]


@router.post(
    "/entities/{entity_id}/article/snapshots/{snapshot_id}/restore",
    response_model=EntityDetail,
)
def restore_article_snapshot(
    entity_id: str,
    snapshot_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityDetail:
    try:
        entity = service.restore_article_snapshot(
            session, ctx.campaign_id, entity_id, snapshot_id
        )
    except (service.EntityNotFound, service.LinkNotFound) as exc:
        raise _not_found(exc) from exc
    return service.to_detail(session, entity)


@router.patch("/entities/{entity_id}", response_model=EntityOut)
def patch_entity(
    entity_id: str,
    body: EntityUpdate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.update_entity(session, ctx.campaign_id, entity_id, data=body)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return service.to_out(session, entity)


@router.delete("/entities/{entity_id}", response_model=EntityOut)
def delete_entity(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.soft_delete_entity(session, ctx.campaign_id, entity_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    except service.InvalidStateTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return service.to_out(session, entity)


@router.post("/entities/purge", response_model=PurgeResult)
def purge_deleted(
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> PurgeResult:
    """Permanently delete every soft-deleted entity in the campaign. Irreversible."""
    purged = service.purge_deleted_entities(session, ctx.campaign_id)
    return PurgeResult(
        count=len(purged), entities=[PurgedEntity(**p) for p in purged]
    )


@router.post("/entities/{entity_id}/restore", response_model=EntityOut)
def restore_entity(
    entity_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.restore_entity(session, ctx.campaign_id, entity_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    except service.InvalidStateTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return service.to_out(session, entity)


# --------------------------------------------------------------------------- #
# Link types & explicit relations
# --------------------------------------------------------------------------- #
@router.get("/link-types", response_model=list[LinkTypeOut])
def get_link_types(
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[LinkTypeOut]:
    return service.list_link_types(session, ctx.campaign_id)


@router.post("/link-types", response_model=LinkTypeOut, status_code=status.HTTP_201_CREATED)
def post_link_type(
    body: LinkTypeCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> LinkTypeOut:
    lt = service.create_link_type(
        session, ctx.campaign_id, label=body.label, inverse_label=body.inverse_label
    )
    return LinkTypeOut(
        id=lt.id, label=lt.label, inverse_label=lt.inverse_label,
        is_semantic=bool(lt.is_semantic), builtin=False,
    )


@router.post("/entities/{entity_id}/links", response_model=EntityDetail)
def post_link(
    entity_id: str,
    body: LinkCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityDetail:
    try:
        entity = service.create_link(
            session, ctx.campaign_id, entity_id,
            to_entity=body.to_entity, link_type_id=body.link_type_id,
            label=body.label, notes=body.notes,
        )
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    except service.LinkCycle as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.InvalidLink as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return service.to_detail(session, entity)


@router.delete("/links/{link_id}", response_model=EntityDetail)
def delete_link(
    link_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityDetail:
    try:
        entity = service.delete_link(session, ctx.campaign_id, link_id)
    except service.LinkNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "link not found") from exc
    except service.InvalidLink as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return service.to_detail(session, entity)


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
@router.get("/tags", response_model=list[TagOut])
def get_tags(
    session: Session = Depends(get_session),
    ctx: CampaignContext = Viewer,
) -> list[TagOut]:
    return [TagOut.model_validate(t) for t in service.list_tags(session, ctx.campaign_id)]


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def post_tag(
    body: TagCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> TagOut:
    tag = service.get_or_create_tag(session, ctx.campaign_id, body.name, body.color)
    session.commit()
    return TagOut.model_validate(tag)


@router.post("/entities/{entity_id}/tags", response_model=EntityOut)
def add_entity_tag(
    entity_id: str,
    body: TagCreate,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.tag_entity(
            session, ctx.campaign_id, entity_id, tag_name=body.name, color=body.color
        )
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return service.to_out(session, entity)


@router.delete("/entities/{entity_id}/tags/{tag_id}", response_model=EntityOut)
def remove_entity_tag(
    entity_id: str,
    tag_id: str,
    session: Session = Depends(get_session),
    ctx: CampaignContext = Editor,
) -> EntityOut:
    try:
        entity = service.untag_entity(session, ctx.campaign_id, entity_id, tag_id)
    except service.EntityNotFound as exc:
        raise _not_found(exc) from exc
    return service.to_out(session, entity)
