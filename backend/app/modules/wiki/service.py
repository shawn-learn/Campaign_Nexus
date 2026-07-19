"""Wiki commands. Every mutation flows through the core command pipeline (ADR-004)."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.wiki import search
from app.modules.wiki.article import extract_mention_ids, extract_plain_text
from app.modules.wiki.models import Entity, EntityTag, Link, LinkType, Tag
from app.modules.wiki.schemas import (
    ENTITY_TYPES,
    EntityCreate,
    EntityDetail,
    EntityOut,
    EntityRef,
    EntityUpdate,
    LinkRef,
    LinkTypeOut,
    TagOut,
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

MENTIONS_LINK_TYPE_ID = "mentions"
WITHIN_LINK_TYPE_ID = "within"

# Built-in link vocabulary (campaign_id NULL). ``acyclic`` types reject cycles on insert.
# (id, label, inverse_label, is_semantic, acyclic)
_BUILTIN_LINK_TYPES: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("mentions", "mentions", "mentioned by", False, False),
    ("within", "within", "contains", True, True),
    ("located_at", "located at", "location of", True, False),
    ("member_of", "member of", "has member", True, False),
    ("ally_of", "ally of", "ally of", False, False),
    ("enemy_of", "enemy of", "enemy of", False, False),
    ("leads_to", "leads to", "reached from", True, False),
    ("given_by", "given by", "gives", True, False),
    ("owns", "owns", "owned by", True, False),
    ("depends_on", "depends on", "unlocks", True, True),
    ("knows_about", "knows about", "known by", True, False),
)
_ACYCLIC_LINK_TYPES = frozenset(t[0] for t in _BUILTIN_LINK_TYPES if t[4])


class UnknownEntityType(ValueError):
    pass


class EntityNotFound(LookupError):
    pass


class InvalidStateTransition(ValueError):
    pass


class InvalidLink(ValueError):
    pass


class LinkCycle(ValueError):
    pass


class LinkNotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Slug helpers
# --------------------------------------------------------------------------- #
def _slugify(name: str) -> str:
    base = _SLUG_STRIP.sub("-", name.lower()).strip("-")
    return base or "entity"


def _unique_slug(session: Session, campaign_id: str, name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while session.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.campaign_id == campaign_id, Entity.slug == slug)
    ):
        slug = f"{base}-{n}"
        n += 1
    return slug


# --------------------------------------------------------------------------- #
# Read + serialization
# --------------------------------------------------------------------------- #
def _tags_for(session: Session, entity_id: str) -> list[TagOut]:
    rows = session.scalars(
        select(Tag)
        .join(EntityTag, EntityTag.tag_id == Tag.id)
        .where(EntityTag.entity_id == entity_id)
        .order_by(Tag.name)
    )
    return [TagOut.model_validate(t) for t in rows]


def to_out(session: Session, entity: Entity) -> EntityOut:
    return EntityOut(
        id=entity.id,
        campaign_id=entity.campaign_id,
        entity_type=entity.entity_type,
        name=entity.name,
        slug=entity.slug,
        summary=entity.summary,
        tags=_tags_for(session, entity.id),
        deleted=entity.deleted_at_real is not None,
        created_at_real=entity.created_at_real,
        updated_at_real=entity.updated_at_real,
    )


def _require_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.campaign_id != campaign_id:
        raise EntityNotFound(entity_id)
    return entity


def get_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    return _require_entity(session, campaign_id, entity_id)


# The browse hub's sort options → (column, descending). ``updated`` falls back to created
# for rows never edited (updated_at defaults to created_at at insert, so no coalesce needed).
_SORTS: dict[str, tuple[Any, bool]] = {
    "created": (Entity.created_at_real, True),
    "-created": (Entity.created_at_real, False),
    "updated": (Entity.updated_at_real, True),
    "-updated": (Entity.updated_at_real, False),
    "name": (func.lower(Entity.name), False),
    "-name": (func.lower(Entity.name), True),
}
_DEFAULT_SORT = "created"


def list_entities(
    session: Session,
    campaign_id: str,
    *,
    entity_type: str | None = None,
    tag_id: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    sort: str | None = None,
) -> list[Entity]:
    stmt = select(Entity).where(Entity.campaign_id == campaign_id)
    if not include_deleted:
        stmt = stmt.where(Entity.deleted_at_real.is_(None))
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    if tag_id:
        stmt = stmt.join(EntityTag, EntityTag.entity_id == Entity.id).where(
            EntityTag.tag_id == tag_id
        )
    if q:
        # Substring match over name + summary — the browse hub's live filter (ranked
        # relevance search over the article body too is ``full_text_search``).
        like = f"%{q}%"
        stmt = stmt.where(or_(Entity.name.ilike(like), Entity.summary.ilike(like)))
    column, descending = _SORTS.get(sort or _DEFAULT_SORT, _SORTS[_DEFAULT_SORT])
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    return list(session.scalars(stmt))


def full_text_search(
    session: Session,
    campaign_id: str,
    query: str,
    *,
    entity_type: str | None = None,
    tag_id: str | None = None,
    limit: int = 20,
) -> list[Entity]:
    """Ranked FTS5 search (NFR-1.2). Returns entities in relevance order."""
    ids = search.search_entity_ids(
        session, campaign_id, query,
        entity_type=entity_type, tag_id=tag_id, limit=limit,
    )
    if not ids:
        return []
    by_id = {
        e.id: e for e in session.scalars(select(Entity).where(Entity.id.in_(ids)))
    }
    return [by_id[i] for i in ids if i in by_id]  # preserve rank order


# --------------------------------------------------------------------------- #
# Links & article
# --------------------------------------------------------------------------- #
def ensure_builtin_link_types(session: Session) -> None:
    """Idempotently seed the shared (campaign_id NULL) built-in link vocabulary."""
    missing = False
    for type_id, label, inverse, semantic, _acyclic in _BUILTIN_LINK_TYPES:
        if session.get(LinkType, type_id) is None:
            session.add(
                LinkType(
                    id=type_id,
                    campaign_id=None,
                    label=label,
                    inverse_label=inverse,
                    is_semantic=semantic,
                )
            )
            missing = True
    if missing:
        session.flush()


def list_link_types(session: Session, campaign_id: str) -> list[LinkTypeOut]:
    ensure_builtin_link_types(session)
    rows = session.scalars(
        select(LinkType)
        .where((LinkType.campaign_id.is_(None)) | (LinkType.campaign_id == campaign_id))
        .order_by(LinkType.label)
    )
    return [
        LinkTypeOut(
            id=lt.id,
            label=lt.label,
            inverse_label=lt.inverse_label,
            is_semantic=bool(lt.is_semantic),
            builtin=lt.campaign_id is None,
        )
        for lt in rows
    ]


def create_link_type(
    session: Session, campaign_id: str, *, label: str, inverse_label: str
) -> LinkType:
    lt = LinkType(
        id=new_id(),
        campaign_id=campaign_id,
        label=label,
        inverse_label=inverse_label,
        is_semantic=False,
    )
    session.add(lt)
    session.commit()
    return lt


def _link_ref(session: Session, link: Link, other_id: str, use_inverse: bool) -> LinkRef | None:
    other = session.get(Entity, other_id)
    if other is None:
        return None
    lt = session.get(LinkType, link.link_type_id)
    label = (lt.inverse_label if use_inverse else lt.label) if lt else link.link_type_id
    return LinkRef(
        link_id=link.id,
        link_type=link.link_type_id,
        label=label,
        source=link.source,
        entity_id=other.id,
        name=other.name,
        entity_type=other.entity_type,
        slug=other.slug,
        deleted=other.deleted_at_real is not None,
    )


def get_links(
    session: Session, campaign_id: str, entity_id: str
) -> tuple[list[LinkRef], list[LinkRef]]:
    outbound_rows = session.scalars(select(Link).where(Link.from_entity == entity_id))
    backlink_rows = session.scalars(select(Link).where(Link.to_entity == entity_id))
    outbound = [
        ref
        for link in outbound_rows
        if (ref := _link_ref(session, link, link.to_entity, use_inverse=False))
    ]
    backlinks = [
        ref
        for link in backlink_rows
        if (ref := _link_ref(session, link, link.from_entity, use_inverse=True))
    ]
    return outbound, backlinks


def _parent_via(session: Session, entity_id: str, link_type_id: str) -> str | None:
    """The single outbound target of a hierarchical link (e.g. a location's parent)."""
    return session.scalar(
        select(Link.to_entity).where(
            Link.from_entity == entity_id, Link.link_type_id == link_type_id
        )
    )


def within_ancestors(session: Session, entity_id: str) -> list[EntityRef]:
    """The 'within' chain from root down to the immediate parent (breadcrumb order)."""
    chain: list[EntityRef] = []
    visited: set[str] = {entity_id}
    current = _parent_via(session, entity_id, WITHIN_LINK_TYPE_ID)
    while current and current not in visited:
        visited.add(current)
        parent = session.get(Entity, current)
        if parent is None:
            break
        chain.append(
            EntityRef(
                entity_id=parent.id,
                name=parent.name,
                entity_type=parent.entity_type,
                slug=parent.slug,
            )
        )
        current = _parent_via(session, current, WITHIN_LINK_TYPE_ID)
    chain.reverse()  # root first
    return chain


def to_detail(session: Session, entity: Entity) -> EntityDetail:
    outbound, backlinks = get_links(session, entity.campaign_id, entity.id)
    base = to_out(session, entity)
    return EntityDetail(
        **base.model_dump(),
        article_json=json.loads(entity.article_json) if entity.article_json else None,
        outbound=outbound,
        backlinks=backlinks,
        ancestors=within_ancestors(session, entity.id),
    )


def _reaches(session: Session, start: str, target: str, link_type_id: str) -> bool:
    """Depth-first: is ``target`` reachable from ``start`` along edges of this type?

    A node may have several outbound edges of an acyclic type (a quest can depend on two
    others), so this walks the whole DAG rather than a single parent chain.
    """
    stack = [start]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(
            session.scalars(
                select(Link.to_entity).where(
                    Link.from_entity == current, Link.link_type_id == link_type_id
                )
            )
        )
    return False


def _would_create_cycle(
    session: Session, from_id: str, to_id: str, link_type_id: str
) -> bool:
    """For an acyclic type, adding from→to cycles iff ``to`` can already reach ``from``."""
    return _reaches(session, to_id, from_id, link_type_id)


def create_link(
    session: Session,
    campaign_id: str,
    from_entity: str,
    *,
    to_entity: str,
    link_type_id: str,
    label: str | None = None,
    notes: str | None = None,
) -> Entity:
    """Create an explicit typed link (relation). Enforces acyclicity for 'within' etc."""
    source = _require_entity(session, campaign_id, from_entity)
    target = _require_entity(session, campaign_id, to_entity)
    if from_entity == to_entity:
        raise InvalidLink("an entity cannot link to itself")

    ensure_builtin_link_types(session)
    link_type = session.get(LinkType, link_type_id)
    if link_type is None or (
        link_type.campaign_id is not None and link_type.campaign_id != campaign_id
    ):
        raise InvalidLink(f"unknown link_type_id: {link_type_id}")

    if link_type_id in _ACYCLIC_LINK_TYPES and _would_create_cycle(
        session, from_entity, to_entity, link_type_id
    ):
        raise LinkCycle(
            f"'{source.name}' {link_type.label} '{target.name}' would create a cycle"
        )

    existing = session.scalar(
        select(Link).where(
            Link.from_entity == from_entity,
            Link.to_entity == to_entity,
            Link.link_type_id == link_type_id,
            Link.source == "explicit",
        )
    )
    if existing is not None:
        return source  # idempotent

    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.add(
            Link(
                id=new_id(),
                campaign_id=campaign_id,
                from_entity=from_entity,
                to_entity=to_entity,
                link_type_id=link_type_id,
                label=label,
                notes=notes,
                source="explicit",
                created_at_real=now_real_iso(),
            )
        )
        ctx.emit(
            "link_added",
            payload={"from": from_entity, "to": to_entity, "type": link_type_id,
                     "source": "explicit"},
            narrative=f"'{source.name}' {link_type.label} '{target.name}'.",
        )
    session.refresh(source)
    return source


def delete_link(session: Session, campaign_id: str, link_id: str) -> Entity:
    """Remove an explicit link. Mention links are managed by the article, not here."""
    link = session.get(Link, link_id)
    if link is None or link.campaign_id != campaign_id:
        raise LinkNotFound(link_id)
    if link.source != "explicit":
        raise InvalidLink("mention links are managed via the article editor")
    from_id = link.from_entity
    lt = session.get(LinkType, link.link_type_id)
    label = lt.label if lt else link.link_type_id
    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.delete(link)
        ctx.emit(
            "link_removed",
            payload={"from": link.from_entity, "to": link.to_entity,
                     "type": link.link_type_id, "source": "explicit"},
            narrative=f"Removed relation '{label}'.",
        )
    source = session.get(Entity, from_id)
    if source is None:
        raise LinkNotFound(from_id)
    return source


def update_article(
    session: Session, campaign_id: str, entity_id: str, *, article_json: dict[str, object]
) -> Entity:
    """Save the article and diff its @mentions into ``mention`` links (FR-2.2/2.3)."""
    entity = _require_entity(session, campaign_id, entity_id)

    # Only mentions that resolve to a real entity in this campaign (and not self) count.
    candidate_ids = [i for i in extract_mention_ids(article_json) if i != entity_id]
    valid_ids = set(
        session.scalars(
            select(Entity.id).where(
                Entity.campaign_id == campaign_id, Entity.id.in_(candidate_ids)
            )
        )
    ) if candidate_ids else set()

    existing = {
        link.to_entity: link
        for link in session.scalars(
            select(Link).where(
                Link.from_entity == entity_id,
                Link.link_type_id == MENTIONS_LINK_TYPE_ID,
                Link.source == "mention",
            )
        )
    }
    to_add = valid_ids - existing.keys()
    to_remove = existing.keys() - valid_ids

    now = now_real_iso()
    with command_tx(session, campaign_id, actor="gm") as ctx:
        # Snapshot the *previous* article before overwriting it (FR-13.4), if it had prose.
        if entity.article_json and entity.article_json != json.dumps(article_json):
            _snapshot_article(session, entity, now)
        entity.article_json = json.dumps(article_json)
        entity.article_text = extract_plain_text(article_json)
        entity.updated_at_real = now
        search.reindex(session, entity)
        ctx.emit(
            "article_edited",
            payload={"entity_id": entity.id, "mentions_added": sorted(to_add),
                     "mentions_removed": sorted(to_remove)},
            narrative=f"Edited article for '{entity.name}'.",
        )
        if to_add:
            ensure_builtin_link_types(session)
        for target_id in to_add:
            session.add(
                Link(
                    id=new_id(),
                    campaign_id=campaign_id,
                    from_entity=entity_id,
                    to_entity=target_id,
                    link_type_id=MENTIONS_LINK_TYPE_ID,
                    source="mention",
                    created_at_real=now,
                )
            )
            ctx.emit(
                "link_added",
                payload={"from": entity_id, "to": target_id, "type": MENTIONS_LINK_TYPE_ID,
                         "source": "mention"},
                narrative=f"'{entity.name}' now mentions an entity.",
            )
        for target_id in to_remove:
            session.delete(existing[target_id])
            ctx.emit(
                "link_removed",
                payload={"from": entity_id, "to": target_id, "type": MENTIONS_LINK_TYPE_ID,
                         "source": "mention"},
                narrative=f"'{entity.name}' no longer mentions an entity.",
            )
    session.refresh(entity)
    return entity


# --------------------------------------------------------------------------- #
# Article snapshots (FR-13.4) + delete-preflight references (FR-13.3)
# --------------------------------------------------------------------------- #
_SNAPSHOT_KEEP = 20


def _snapshot_article(session: Session, entity: Entity, now: str) -> None:
    """Record the entity's current article as a version, capped at ``_SNAPSHOT_KEEP``."""
    from app.modules.wiki.models import ArticleSnapshot  # local: avoids a cycle at import

    preview = (entity.article_text or "")[:140]
    session.add(
        ArticleSnapshot(
            id=new_id(), entity_id=entity.id, campaign_id=entity.campaign_id,
            article_json=entity.article_json or "{}", preview=preview, created_at_real=now,
        )
    )
    session.flush()
    stale = list(
        session.scalars(
            select(ArticleSnapshot.id)
            .where(ArticleSnapshot.entity_id == entity.id)
            # rowid is strictly insertion-ordered — a deterministic tiebreak when
            # created_at_real ties (coarse OS clocks stamp rapid edits identically).
            .order_by(ArticleSnapshot.created_at_real.desc(), text("article_snapshot.rowid DESC"))
            .offset(_SNAPSHOT_KEEP)
        )
    )
    if stale:
        from sqlalchemy import delete as sa_delete

        session.execute(
            sa_delete(ArticleSnapshot).where(ArticleSnapshot.id.in_(stale))
        )


def list_article_snapshots(session: Session, campaign_id: str, entity_id: str) -> list[Any]:
    from app.modules.wiki.models import ArticleSnapshot

    _require_entity(session, campaign_id, entity_id)
    return list(
        session.scalars(
            select(ArticleSnapshot)
            .where(ArticleSnapshot.entity_id == entity_id)
            # rowid tiebreak keeps ordering deterministic when timestamps tie.
            .order_by(ArticleSnapshot.created_at_real.desc(), text("article_snapshot.rowid DESC"))
        )
    )


def restore_article_snapshot(
    session: Session, campaign_id: str, entity_id: str, snapshot_id: str
) -> Entity:
    """Roll the article back to a snapshot (which itself snapshots the current version first)."""
    from app.modules.wiki.models import ArticleSnapshot

    snapshot = session.get(ArticleSnapshot, snapshot_id)
    if snapshot is None or snapshot.entity_id != entity_id or snapshot.campaign_id != campaign_id:
        raise LinkNotFound(snapshot_id)
    return update_article(
        session, campaign_id, entity_id, article_json=json.loads(snapshot.article_json)
    )


def references_to(session: Session, campaign_id: str, entity_id: str) -> list[LinkRef]:
    """Everything in the knowledge graph that points *at* this entity — the delete-preflight.

    These are the edges that would be severed (or dangle) if the entity were removed:
    backlinks of every type (located_at, member_of, depends_on, mentions, knows_about …).
    Atlas markers and NPC givers are resolved at the orchestration layer (they live above
    the wiki); here we answer the graph question, which is the bulk of it.
    """
    _require_entity(session, campaign_id, entity_id)
    rows = session.scalars(select(Link).where(Link.to_entity == entity_id))
    refs = [
        ref
        for link in rows
        if (ref := _link_ref(session, link, link.from_entity, use_inverse=True))
    ]
    return refs


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def create_entity(
    session: Session, campaign_id: str, *, data: EntityCreate, created_by: str
) -> Entity:
    if data.entity_type not in ENTITY_TYPES:
        raise UnknownEntityType(data.entity_type)

    now = now_real_iso()
    entity = Entity(
        id=new_id(),
        campaign_id=campaign_id,
        entity_type=data.entity_type,
        name=data.name,
        slug=_unique_slug(session, campaign_id, data.name),
        summary=data.summary,
        created_by=created_by,
        created_at_real=now,
        updated_at_real=now,
    )
    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.add(entity)
        session.flush()
        search.reindex(session, entity)
        ctx.emit(
            "entity_created",
            payload={"entity_id": entity.id, "entity_type": entity.entity_type,
                     "name": entity.name},
            narrative=f"Created {entity.entity_type} '{entity.name}'.",
        )
    session.refresh(entity)
    return entity


def update_entity(
    session: Session, campaign_id: str, entity_id: str, *, data: EntityUpdate
) -> Entity:
    entity = _require_entity(session, campaign_id, entity_id)
    changes: dict[str, object] = {}

    if data.name is not None and data.name != entity.name:
        changes["name"] = {"from": entity.name, "to": data.name}
        entity.name = data.name
    if data.summary_set and data.summary != entity.summary:
        changes["summary"] = {"from": entity.summary, "to": data.summary}
        entity.summary = data.summary

    if not changes:
        return entity  # nothing to do; no event for a no-op edit

    entity.updated_at_real = now_real_iso()
    with command_tx(session, campaign_id, actor="gm") as ctx:
        search.reindex(session, entity)
        ctx.emit(
            "entity_updated",
            payload={"entity_id": entity.id, "changes": changes},
            narrative=f"Updated {entity.entity_type} '{entity.name}'.",
        )
    session.refresh(entity)
    return entity


def soft_delete_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    entity = _require_entity(session, campaign_id, entity_id)
    if entity.deleted_at_real is not None:
        raise InvalidStateTransition("entity already deleted")
    entity.deleted_at_real = now_real_iso()
    entity.updated_at_real = entity.deleted_at_real
    with command_tx(session, campaign_id, actor="gm") as ctx:
        search.reindex(session, entity)  # drops it from the index
        ctx.emit(
            "entity_deleted",
            payload={"entity_id": entity.id, "entity_type": entity.entity_type,
                     "name": entity.name},
            narrative=f"Deleted {entity.entity_type} '{entity.name}'.",
        )
    session.refresh(entity)
    return entity


def restore_entity(session: Session, campaign_id: str, entity_id: str) -> Entity:
    entity = _require_entity(session, campaign_id, entity_id)
    if entity.deleted_at_real is None:
        raise InvalidStateTransition("entity is not deleted")
    entity.deleted_at_real = None
    entity.updated_at_real = now_real_iso()
    with command_tx(session, campaign_id, actor="gm") as ctx:
        search.reindex(session, entity)  # re-adds it to the index
        ctx.emit(
            "entity_restored",
            payload={"entity_id": entity.id, "entity_type": entity.entity_type,
                     "name": entity.name},
            narrative=f"Restored {entity.entity_type} '{entity.name}'.",
        )
    session.refresh(entity)
    return entity


def purge_deleted_entities(session: Session, campaign_id: str) -> list[dict[str, str]]:
    """Permanently remove every soft-deleted entity in the campaign. Irreversible.

    Soft delete only stamps ``deleted_at_real``, so the row and its module extensions
    (Npc, Merchant, Encounter, …) survive forever. This is the only way to actually
    reclaim them. Dependent rows go with it: ``ondelete="CASCADE"`` drops the owned
    extensions, ``SET NULL`` clears references from surviving rows, and SQLite enforces
    both (``PRAGMA foreign_keys=ON``, ADR-002).

    The event log is deliberately left alone — it is immutable, and events naming a
    purged entity keep naming it. ``chronicle.projectors`` skips ids with no surviving
    entity so a projection rebuild still succeeds.

    Returns what was purged (id / type / name), so the caller can report it.
    """
    entities = list(
        session.scalars(
            select(Entity).where(
                Entity.campaign_id == campaign_id,
                Entity.deleted_at_real.is_not(None),
            )
        )
    )
    if not entities:
        return []
    purged = [
        {"id": e.id, "entity_type": e.entity_type, "name": e.name} for e in entities
    ]
    with command_tx(session, campaign_id, actor="gm") as ctx:
        for entity in entities:
            search.remove_entity(session, entity.id)
            session.delete(entity)
        ctx.emit(
            "entities_purged",
            payload={"count": len(purged), "entities": purged},
            narrative=(
                f"Permanently deleted {len(purged)} "
                f"soft-deleted {'entity' if len(purged) == 1 else 'entities'}."
            ),
        )
    return purged


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
def list_tags(session: Session, campaign_id: str) -> list[Tag]:
    return list(
        session.scalars(
            select(Tag).where(Tag.campaign_id == campaign_id).order_by(Tag.name)
        )
    )


def get_or_create_tag(
    session: Session, campaign_id: str, name: str, color: str | None = None
) -> Tag:
    name = name.strip()
    tag = session.scalar(
        select(Tag).where(Tag.campaign_id == campaign_id, Tag.name == name)
    )
    if tag is None:
        tag = Tag(id=new_id(), campaign_id=campaign_id, name=name, color=color)
        session.add(tag)
        session.flush()
    return tag


def tag_entity(
    session: Session, campaign_id: str, entity_id: str, *, tag_name: str, color: str | None = None
) -> Entity:
    entity = _require_entity(session, campaign_id, entity_id)
    tag = get_or_create_tag(session, campaign_id, tag_name, color)
    exists = session.get(EntityTag, {"entity_id": entity_id, "tag_id": tag.id})
    if exists is not None:
        return entity  # idempotent; no event for a redundant tag
    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.add(EntityTag(entity_id=entity_id, tag_id=tag.id))
        session.flush()
        search.reindex(session, entity)
        ctx.emit(
            "entity_tagged",
            payload={"entity_id": entity_id, "tag_id": tag.id, "tag": tag.name},
            narrative=f"Tagged '{entity.name}' with #{tag.name}.",
        )
    return entity


def untag_entity(session: Session, campaign_id: str, entity_id: str, tag_id: str) -> Entity:
    entity = _require_entity(session, campaign_id, entity_id)
    link = session.get(EntityTag, {"entity_id": entity_id, "tag_id": tag_id})
    if link is None:
        return entity
    tag = session.get(Tag, tag_id)
    tag_name = tag.name if tag else tag_id
    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.delete(link)
        session.flush()
        search.reindex(session, entity)
        ctx.emit(
            "entity_untagged",
            payload={"entity_id": entity_id, "tag_id": tag_id, "tag": tag_name},
            narrative=f"Removed #{tag_name} from '{entity.name}'.",
        )
    return entity
