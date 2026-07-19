from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Sprint 1 entity-type vocabulary (registry accepts these; extensions come later).
ENTITY_TYPES = (
    "note",
    "npc",
    "location",
    "faction",
    "quest",
    "monster",
    "item",
    "equipment",
    "merchant",
    "map",
    "encounter",
    "skill_challenge",
    "random_table",
    "pc",
    "session",
    "story_node",
)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str | None


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str | None = None


class EntityCreate(BaseModel):
    entity_type: str = Field(examples=["note"])
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None


class EntityUpdate(BaseModel):
    """Partial update. Unset fields are left unchanged; ``summary=None`` clears it."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    summary_set: bool = Field(
        default=False, description="Set true to apply summary (including clearing to null)."
    )


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    entity_type: str
    name: str
    slug: str
    summary: str | None
    tags: list[TagOut] = []
    deleted: bool = False
    created_at_real: str
    updated_at_real: str


class PurgedEntity(BaseModel):
    """One entity that a purge destroyed — enough to report what went, nothing more."""

    id: str
    entity_type: str
    name: str


class PurgeResult(BaseModel):
    count: int
    entities: list[PurgedEntity] = []


class ArticleUpdate(BaseModel):
    """Full replace of the article body (Tiptap/ProseMirror JSON document)."""

    article_json: dict[str, object]


class LinkRef(BaseModel):
    """One end of a link as seen from an entity: the *other* entity + the relation."""

    link_id: str
    link_type: str
    label: str  # the relation word to display (e.g. 'mentions' / 'mentioned by')
    source: str
    entity_id: str
    name: str
    entity_type: str
    slug: str
    deleted: bool


class EntityRef(BaseModel):
    """Bare reference used for breadcrumb ancestors."""

    entity_id: str
    name: str
    entity_type: str
    slug: str


class ReferencesOut(BaseModel):
    """Delete-preflight (FR-13.3): the graph edges pointing at an entity."""

    entity_id: str
    inbound: list[LinkRef]


class ArticleSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    preview: str
    created_at_real: str


class LinkTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    inverse_label: str
    is_semantic: bool
    builtin: bool = False


class LinkTypeCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    inverse_label: str = Field(min_length=1, max_length=60)


class LinkCreate(BaseModel):
    to_entity: str
    link_type_id: str
    label: str | None = None
    notes: str | None = None


class EntityDetail(EntityOut):
    """Single-entity view: adds the article body and the link neighborhood."""

    article_json: dict[str, object] | None = None
    outbound: list[LinkRef] = []
    backlinks: list[LinkRef] = []
    ancestors: list[EntityRef] = []  # 'within' chain, root → parent (breadcrumb)
