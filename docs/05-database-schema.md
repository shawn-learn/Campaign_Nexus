# 7. Database Schema

Target: **SQLite** (WAL, `foreign_keys=ON`), managed by SQLAlchemy 2.0 + Alembic. DDL below is
the design reference; the ORM models are the implementation source of truth.

Conventions:
- Primary keys: `TEXT` UUIDv7 (time-ordered → index-friendly, merge-safe for future sharing).
- Timestamps: `*_real` = ISO-8601 UTC text; `*_game` = INTEGER minutes since campaign epoch
  (may be negative for pre-campaign history).
- Booleans: INTEGER 0/1. JSON: TEXT validated at the application layer (JSON1 for queries).
- Every campaign-owned table has `campaign_id` + composite indexes led by it (NFR-6.2).
- Soft delete: `deleted_at_real NULL` on entity registry only; child rows follow their entity.

---

## 7.1 Accounts & campaign

```sql
CREATE TABLE user (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  password_hash TEXT,                    -- NULL in local single-user mode
  created_at_real TEXT NOT NULL
);

CREATE TABLE rule_system (               -- registry of installed plugins
  id           TEXT PRIMARY KEY,         -- 'dnd5e', 'nimble'
  name         TEXT NOT NULL,
  version      TEXT NOT NULL,            -- plugin semver; sheets record schema_version
  enabled      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE campaign (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  description    TEXT,
  rule_system_id TEXT NOT NULL REFERENCES rule_system(id),
  calendar_json  TEXT NOT NULL,          -- CalendarDefinition (immutable once events exist)
  clock_time_game INTEGER NOT NULL DEFAULT 0,   -- the campaign clock (minutes since epoch)
  campaign_start_game INTEGER NOT NULL DEFAULT 0,
  settings_json  TEXT NOT NULL DEFAULT '{}',
  created_by     TEXT NOT NULL REFERENCES user(id),
  created_at_real TEXT NOT NULL,
  archived_at_real TEXT
);

CREATE TABLE campaign_member (
  campaign_id TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  user_id     TEXT NOT NULL REFERENCES user(id),
  role        TEXT NOT NULL CHECK (role IN ('owner','editor','viewer')),
  PRIMARY KEY (campaign_id, user_id)
);
```

The clock lives on `campaign` (one row, hot column) rather than a separate table — updated only
via the time-engine command (enforced in code, ADR-004).

## 7.2 Entity registry, links, tags (World Graph core)

```sql
CREATE TABLE entity (
  id           TEXT PRIMARY KEY,
  campaign_id  TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  entity_type  TEXT NOT NULL,            -- 'location','npc','faction','quest','monster','item',
                                         -- 'map','encounter','pc','session','story_node','note'
  name         TEXT NOT NULL,
  slug         TEXT NOT NULL,            -- unique per campaign; stable URL id
  summary      TEXT,                     -- one-liner for hovers/search results
  article_json TEXT,                     -- Tiptap doc (rich text with mention nodes)
  article_text TEXT,                     -- plain-text rendering (FTS + AI substrate)
  portrait_media_id TEXT REFERENCES media(id),
  created_by   TEXT NOT NULL REFERENCES user(id),
  created_at_real TEXT NOT NULL,
  updated_at_real TEXT NOT NULL,
  deleted_at_real TEXT,                  -- soft delete (NFR-2.4)
  UNIQUE (campaign_id, slug)
);
CREATE INDEX ix_entity_campaign_type ON entity(campaign_id, entity_type)
  WHERE deleted_at_real IS NULL;
CREATE INDEX ix_entity_campaign_name ON entity(campaign_id, name);

CREATE TABLE link_type (
  id          TEXT PRIMARY KEY,          -- 'within','member_of','mentions',...
  campaign_id TEXT REFERENCES campaign(id) ON DELETE CASCADE,  -- NULL = built-in
  label       TEXT NOT NULL,
  inverse_label TEXT NOT NULL,           -- rendered on the backlink side ('contains', ...)
  is_semantic INTEGER NOT NULL DEFAULT 0 -- engine-interpreted (within, located_at, depends_on)
);

CREATE TABLE link (
  id           TEXT PRIMARY KEY,
  campaign_id  TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  from_entity  TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  to_entity    TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  link_type_id TEXT NOT NULL REFERENCES link_type(id),
  label        TEXT,                     -- free-text qualifier ('estranged brother')
  notes        TEXT,
  source       TEXT NOT NULL DEFAULT 'explicit' CHECK (source IN ('explicit','mention')),
  valid_from_game INTEGER,               -- optional historical validity
  valid_to_game   INTEGER,
  created_at_real TEXT NOT NULL,
  UNIQUE (from_entity, to_entity, link_type_id, source)
);
CREATE INDEX ix_link_from ON link(from_entity, link_type_id);
CREATE INDEX ix_link_to   ON link(to_entity, link_type_id);      -- backlinks (FR-2.3)

CREATE TABLE tag (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  color       TEXT,
  UNIQUE (campaign_id, name)
);
CREATE TABLE entity_tag (
  entity_id TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  tag_id    TEXT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, tag_id)
);
```

### Traversal examples (design validation)

Backlinks: `SELECT ... FROM link WHERE to_entity = :id` (indexed).
Location breadcrumb (leaf → world) via recursive CTE over `link` where
`link_type_id='within'`; cycle-guarded in the application before insert.

## 7.3 Entity extensions

One 1:1 table per structured type; all share `entity_id` PK → FK to registry.

```sql
CREATE TABLE location (
  entity_id    TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  location_kind TEXT NOT NULL,           -- world|region|country|city|district|building|dungeon|room|poi
  population   INTEGER,
  extras_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE npc (
  entity_id    TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'alive',   -- alive|dead|missing|unknown|retired
  current_location_id TEXT REFERENCES entity(id),  -- PROJECTION of npc_relocated events
  has_met_party INTEGER NOT NULL DEFAULT 0,        -- PROJECTION
  last_party_interaction_game INTEGER,             -- PROJECTION
  goals        TEXT,
  secrets      TEXT,                     -- GM-only by nature (whole app is GM-only)
  voice_notes  TEXT,
  stat_block_id TEXT REFERENCES stat_block(id),
  extras_json  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_npc_location ON npc(current_location_id);
CREATE INDEX ix_npc_status   ON npc(status);

CREATE TABLE faction (
  entity_id   TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  faction_kind TEXT, motto TEXT, influence TEXT,
  extras_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE item (
  entity_id   TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  rarity TEXT, requires_attunement INTEGER DEFAULT 0,
  stat_block_id TEXT REFERENCES stat_block(id),
  extras_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE monster (
  entity_id     TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  stat_block_id TEXT NOT NULL REFERENCES stat_block(id),
  source        TEXT NOT NULL DEFAULT 'custom',  -- 'content_pack:<pack>@<ver>' | 'custom'
  variant_of    TEXT REFERENCES entity(id),      -- variants (FR-11.4)
  -- facet columns generated from the stat block for fast filtering (populated by plugin):
  facet1_num REAL, facet2_num REAL, facet1_text TEXT, facet2_text TEXT
  -- e.g. 5e: facet1_num=CR, facet1_text=creature type; meaning declared by plugin manifest
);
CREATE INDEX ix_monster_facets ON monster(facet1_num, facet1_text);

CREATE TABLE pc (
  entity_id   TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  player_name TEXT,
  status_json TEXT NOT NULL DEFAULT '{}',   -- live resources: HP, slots, conditions (plugin-shaped)
  stat_block_id TEXT NOT NULL REFERENCES stat_block(id)
);
```

## 7.4 Rules-engine storage

```sql
CREATE TABLE stat_block (
  id             TEXT PRIMARY KEY,
  campaign_id    TEXT REFERENCES campaign(id) ON DELETE CASCADE,  -- NULL = shared content pack
  rule_system_id TEXT NOT NULL REFERENCES rule_system(id),
  sheet_type     TEXT NOT NULL,          -- 'pc'|'npc'|'monster'|'item'
  schema_version TEXT NOT NULL,          -- plugin schema the doc validates against
  doc_json       TEXT NOT NULL,          -- the entire system-specific sheet
  derived_json   TEXT NOT NULL DEFAULT '{}'  -- plugin-computed cache (AC, save DCs, ...)
);
```

Content packs ship as JSON files inside plugins; an import step materializes them into
`entity` + `monster` + `stat_block` rows per campaign (or shared with `campaign_id NULL` and
copy-on-write into campaigns when customized).

## 7.5 Chronicle: events, timeline, sessions

```sql
CREATE TABLE session (
  entity_id      TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  session_number INTEGER NOT NULL,
  real_date      TEXT,
  status         TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','live','completed')),
  clock_start_game INTEGER, clock_end_game INTEGER,
  summary        TEXT,
  notes_json     TEXT NOT NULL DEFAULT '{}',   -- decisions, discoveries, loot, xp
  UNIQUE (entity_id, session_number)
);
-- invariant "≤1 live session per campaign" enforced in the session service transaction

CREATE TABLE domain_event (
  id              TEXT PRIMARY KEY,
  campaign_id     TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  seq             INTEGER NOT NULL,       -- per-campaign monotonic (allocated in tx)
  event_type      TEXT NOT NULL,          -- catalog in 06-event-sourcing.md
  occurred_at_game INTEGER NOT NULL,
  recorded_at_real TEXT NOT NULL,
  session_id      TEXT REFERENCES session(entity_id),
  actor           TEXT NOT NULL,          -- 'gm'|'time_engine'|'story_engine'|'combat'|'import'
  payload_json    TEXT NOT NULL,
  narrative_text  TEXT NOT NULL,          -- human-readable one-liner (timeline + AI substrate)
  UNIQUE (campaign_id, seq)
);
CREATE INDEX ix_event_time    ON domain_event(campaign_id, occurred_at_game);
CREATE INDEX ix_event_session ON domain_event(session_id);
CREATE INDEX ix_event_type    ON domain_event(campaign_id, event_type);

CREATE TABLE event_entity (                -- events ↔ entities (filtering, FR-8.3)
  event_id  TEXT NOT NULL REFERENCES domain_event(id) ON DELETE CASCADE,
  entity_id TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'subject',   -- subject|location|instrument
  PRIMARY KEY (event_id, entity_id, role)
);
CREATE INDEX ix_event_entity_entity ON event_entity(entity_id);

CREATE TABLE timeline_entry (              -- curated projection + manual lore entries
  id            TEXT PRIMARY KEY,
  campaign_id   TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  event_id      TEXT REFERENCES domain_event(id),   -- NULL for manual lore entries
  occurred_at_game INTEGER NOT NULL,
  title         TEXT NOT NULL,
  body          TEXT,
  icon          TEXT,
  significance  INTEGER NOT NULL DEFAULT 2,  -- 1 minor .. 4 era-defining
  is_hidden     INTEGER NOT NULL DEFAULT 0   -- GM can prune noise without deleting facts
);
CREATE INDEX ix_timeline_time ON timeline_entry(campaign_id, occurred_at_game);

CREATE TABLE npc_location_history (        -- projection of npc_relocated (FR-6.2)
  id          TEXT PRIMARY KEY,
  npc_id      TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  location_id TEXT REFERENCES entity(id),
  from_game   INTEGER NOT NULL,
  to_game     INTEGER,                     -- NULL = current
  cause_event_id TEXT NOT NULL REFERENCES domain_event(id)
);
CREATE INDEX ix_nlh_npc ON npc_location_history(npc_id, from_game);
```

"Where was NPC X at time T": `WHERE npc_id=:x AND from_game<=:t AND (to_game IS NULL OR
to_game>:t)` — one indexed range probe. "During session 7": resolve the session's clock span,
same query.

## 7.6 Time engine

```sql
CREATE TABLE scheduled_event (
  id            TEXT PRIMARY KEY,
  campaign_id   TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  fire_at_game  INTEGER NOT NULL,
  recurrence_json TEXT,                   -- NULL = one-shot; interval or calendar rule
  action_type   TEXT NOT NULL,            -- narrate|move_npc|set_flag|quest_status|activate_story_node|custom
  action_json   TEXT NOT NULL,
  title         TEXT NOT NULL,
  created_by_kind TEXT NOT NULL,          -- gm|npc_schedule|quest_deadline|story_engine
  source_entity_id TEXT REFERENCES entity(id),   -- e.g. the NPC whose itinerary this is
  status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','fired','cancelled'))
);
CREATE INDEX ix_sched_due ON scheduled_event(campaign_id, status, fire_at_game);

CREATE TABLE npc_schedule (                -- recurring itineraries (FR-6.5)
  id          TEXT PRIMARY KEY,
  npc_id      TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  label       TEXT NOT NULL DEFAULT '',
  rule_json   TEXT NOT NULL,               -- {"interval_days":1,"stops":[{"at_seconds",…}]}
  active      INTEGER NOT NULL DEFAULT 1,
  materialized_through_game INTEGER        -- how far the lazy compiler has run (§9.6)
);
```

## 7.7 Playbook

```sql
CREATE TABLE party (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL UNIQUE REFERENCES campaign(id) ON DELETE CASCADE,
  current_location_id TEXT REFERENCES entity(id),   -- projection of party_moved
  gold        INTEGER NOT NULL DEFAULT 0,
  inventory_json TEXT NOT NULL DEFAULT '[]',
  reputation_json TEXT NOT NULL DEFAULT '{}'        -- faction_id -> score
);
CREATE TABLE party_member (
  party_id TEXT NOT NULL REFERENCES party(id) ON DELETE CASCADE,
  pc_id    TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  active   INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (party_id, pc_id)
);

CREATE TABLE quest (
  entity_id  TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  quest_type TEXT NOT NULL DEFAULT 'side' CHECK (quest_type IN ('main','side','hidden')),
  status     TEXT NOT NULL DEFAULT 'unknown'
             CHECK (status IN ('unknown','available','active','completed','failed','expired','abandoned')),
  giver_npc_id TEXT REFERENCES entity(id),
  rewards_json TEXT NOT NULL DEFAULT '{}',
  deadline_game INTEGER,                   -- registers a quest_deadline scheduled_event
  objectives_json TEXT NOT NULL DEFAULT '[]'   -- completion checklist [{"text","done"}]
);
-- dependencies are 'depends_on' links (semantic, acyclic); DAG-checked on insert

CREATE TABLE encounter (
  entity_id  TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  terrain TEXT, environment_json TEXT NOT NULL DEFAULT '[]',
  hazards_json TEXT NOT NULL DEFAULT '[]', tactics TEXT,
  difficulty_cache TEXT                    -- plugin-computed vs current party; recomputed on read
);
CREATE TABLE encounter_combatant (
  id           TEXT PRIMARY KEY,
  encounter_id TEXT NOT NULL REFERENCES encounter(entity_id) ON DELETE CASCADE,
  entity_id    TEXT NOT NULL REFERENCES entity(id),   -- monster or npc
  count        INTEGER NOT NULL DEFAULT 1,
  side         TEXT NOT NULL DEFAULT 'foe' CHECK (side IN ('foe','ally','neutral'))
);

CREATE TABLE combat_run (
  id           TEXT PRIMARY KEY,
  campaign_id  TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  encounter_id TEXT REFERENCES encounter(entity_id),  -- NULL = ad-hoc combat
  session_id   TEXT REFERENCES session(entity_id),
  started_at_game INTEGER NOT NULL,
  status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','abandoned')),
  fold_cursor  INTEGER NOT NULL DEFAULT 0,  -- undo/redo pointer into combat_action.seq
  snapshot_json TEXT                         -- fold cache at cursor (fast reload)
);
CREATE TABLE combat_action (                 -- the event-sourced combat log (ADR-005)
  combat_run_id TEXT NOT NULL REFERENCES combat_run(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  action_type   TEXT NOT NULL,   -- roll_initiative|damage|heal|temp_hp|condition_add|condition_remove|
                                 -- next_turn|concentration_start|concentration_end|legendary_use|
                                 -- lair_trigger|combatant_add|combatant_remove|round_advance|note
  payload_json  TEXT NOT NULL,
  recorded_at_real TEXT NOT NULL,
  PRIMARY KEY (combat_run_id, seq)
);
```

## 7.8 Story engine

```sql
CREATE TABLE campaign_flag (
  campaign_id TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  key         TEXT NOT NULL,
  value_json  TEXT NOT NULL,
  updated_at_game INTEGER NOT NULL,
  updated_by_event TEXT REFERENCES domain_event(id),
  PRIMARY KEY (campaign_id, key)
);

CREATE TABLE story_node (
  entity_id  TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  status     TEXT NOT NULL DEFAULT 'possible'
             CHECK (status IN ('possible','active','resolved','abandoned')),
  pos_x REAL NOT NULL DEFAULT 0, pos_y REAL NOT NULL DEFAULT 0,   -- graph layout
  consequences_json TEXT NOT NULL DEFAULT '[]'   -- ordered action list (validated DSL)
);
CREATE TABLE story_edge (
  id        TEXT PRIMARY KEY,
  from_node TEXT NOT NULL REFERENCES story_node(entity_id) ON DELETE CASCADE,
  to_node   TEXT NOT NULL REFERENCES story_node(entity_id) ON DELETE CASCADE,
  condition_expr TEXT,                     -- predicate DSL source (parsed & validated on save)
  label     TEXT
);
```

## 7.9 Maps & media

```sql
CREATE TABLE media (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,               -- image|map_image|handout
  filename    TEXT NOT NULL, mime TEXT NOT NULL, bytes INTEGER NOT NULL,
  storage_path TEXT NOT NULL,              -- media/ folder, content-addressed name
  created_at_real TEXT NOT NULL
);

CREATE TABLE map (
  entity_id   TEXT PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
  media_id    TEXT NOT NULL REFERENCES media(id),
  width_px INTEGER NOT NULL, height_px INTEGER NOT NULL,
  tiles_ready INTEGER NOT NULL DEFAULT 0,  -- deep-zoom pyramid generated
  location_id TEXT REFERENCES entity(id),  -- the place this map depicts
  parent_map_id TEXT REFERENCES map(entity_id),
  map_kind    TEXT NOT NULL                -- world|region|city|dungeon|building
);
CREATE TABLE map_marker (
  id        TEXT PRIMARY KEY,
  map_id    TEXT NOT NULL REFERENCES map(entity_id) ON DELETE CASCADE,
  x REAL NOT NULL, y REAL NOT NULL,        -- pixel coords in source image space
  icon      TEXT, color TEXT,
  target_entity_id TEXT REFERENCES entity(id) ON DELETE SET NULL,
  child_map_id     TEXT REFERENCES map(entity_id) ON DELETE SET NULL,
  note      TEXT,
  layer     TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX ix_marker_map ON map_marker(map_id);
CREATE TABLE map_region (
  id        TEXT PRIMARY KEY,
  map_id    TEXT NOT NULL REFERENCES map(entity_id) ON DELETE CASCADE,
  name      TEXT,
  polygon_json TEXT NOT NULL,              -- [[x,y],...]; ring is implicit
  color     TEXT,
  target_entity_id TEXT REFERENCES entity(id) ON DELETE SET NULL,
  child_map_id     TEXT REFERENCES map(entity_id) ON DELETE SET NULL,
  note TEXT, layer TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX ix_map_region_map ON map_region(map_id);
```

## 7.10 Search (FTS5)

```sql
CREATE VIRTUAL TABLE entity_fts USING fts5(
  name, summary, article_text, tags,
  content='',                              -- contentless; app maintains rows
  tokenize = 'unicode61 remove_diacritics 2'
);
-- rowid mapping table entity_fts_map(rowid INTEGER PK, entity_id TEXT UNIQUE)
```

Maintained by the entity service on every create/update/delete (same transaction), not by DB
triggers — keeps logic in one language and testable. Search query = FTS match + `campaign_id`
join + type/tag filters + bm25 rank boosted by entity name prefix hits.

## 7.11 Integrity & migration notes

- **Cycle checks** (location `within`, quest `depends_on`, `parent_map`) run in the service
  layer inside the insert transaction (recursive CTE reachability probe).
- **Projections** (`npc.current_location_id`, `party.current_location_id`,
  `npc_location_history`, `timeline_entry`, session auto-links) are written **only** by event
  handlers in the same transaction as their event (ADR-004). A `rebuild-projections` CLI
  command re-derives all of them from `domain_event` — the recovery hatch and the test oracle.
- **Alembic**: every migration autogenerated then hand-reviewed; data backfills as explicit
  steps; a backup file copy is taken automatically before applying migrations (NFR-2.2).
- **PostgreSQL portability** (NFR-5.2): UUID text keys, ISO timestamps, JSON text, and ANSI
  DDL all port; the FTS5 module and JSON1 syntax are wrapped behind `SearchRepository` and
  facet-population code — the two places a PG port touches.
