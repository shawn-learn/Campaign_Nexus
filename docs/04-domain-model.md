# 6. Domain Model

The domain is decomposed into eight bounded contexts. Each maps to one backend module
(ADR-001) and owns its tables (see [Database Schema](05-database-schema.md)).

```
┌────────────────────────────────────────────────────────────────────────┐
│                            CAMPAIGN NEXUS                              │
│                                                                        │
│  ┌───────────────┐   ┌───────────────┐   ┌────────────────────────┐   │
│  │   Campaign     │   │  World Graph  │   │      Chronicle          │   │
│  │  (accounts,    │   │ (entities,    │   │ (domain events,         │   │
│  │   membership)  │   │  links, maps) │   │  timeline, sessions)    │   │
│  └───────┬───────┘   └───────┬───────┘   └───────────┬────────────┘   │
│          │                   │                        │                │
│  ┌───────┴───────┐   ┌───────┴───────┐   ┌───────────┴────────────┐   │
│  │  Time Engine  │   │ Story Engine  │   │       Playbook          │   │
│  │ (clock,       │   │ (nodes, state │   │ (quests, encounters,    │   │
│  │  calendar,    │   │  flags,       │   │  combat runs, party)    │   │
│  │  schedule)    │   │  triggers)    │   │                         │   │
│  └───────────────┘   └───────────────┘   └────────────────────────┘   │
│                                                                        │
│  ┌───────────────┐   ┌────────────────────────────────────────────┐   │
│  │ Rules Engine  │   │                 Search                      │   │
│  │ (plugins,     │   │ (FTS index, tags — read-model over all)     │   │
│  │  stat blocks) │   └────────────────────────────────────────────┘   │
│  └───────────────┘                                                    │
└────────────────────────────────────────────────────────────────────────┘
```

Dependency direction: everything may depend on **Campaign** (scoping) and **Chronicle**
(emitting events). **Rules Engine** is a leaf dependency (pure logic, no dependencies on
other contexts). **Search** and **Story Engine** react to events via the bus — nobody
depends on them.

---

## 6.1 Core abstraction: the Entity

Every wiki-visible thing — NPC, location, faction, quest, monster, item, map, encounter, PC,
story node, session — is an **Entity**: a row in a polymorphic registry carrying the universal
capabilities, plus a type-specific extension record.

**Universal capabilities (the registry guarantees these for every entity type):**
- Identity: `id` (UUIDv7), `campaign_id`, `entity_type`, `name`, `slug`
- Article: rich-text body (Tiptap JSON) with `@mentions`
- Linkability: may be source or target of any `Link`
- Taggability, searchability (FTS-indexed), soft-delete, audit (`created_by/at`, `updated_at`)

This is the keystone decision of the model: **links, tags, search, mentions, and timeline
references are implemented once**, against the registry, and every current and future entity
type inherits them (NFR-4.2). Type-specific data lives in extension tables (`npc`, `location`,
`quest`, …) joined 1:1 by `entity_id`.

## 6.2 Link (typed edge)

`Link(id, campaign_id, from_entity, to_entity, link_type, label, notes, valid_from_time?,
valid_to_time?, source)` where `source ∈ {explicit, mention}`.

- **Explicit links** are relationships the GM asserts (NPC `member_of` Faction, Quest
  `given_by` NPC, Location `within` Region, Map `child_of` Map).
- **Mention links** are derived from `@mentions` in article text on save (diffed: mentions
  added/removed ⇒ links added/removed).
- Bidirectionality is a query property (ADR-003): backlinks = `WHERE to_entity = :id`.
- Optional campaign-time validity supports historical truth ("was a member until day 210").

**Link-type vocabulary** is a per-campaign extensible dictionary seeded with a standard set
(`within`, `member_of`, `ally_of`, `enemy_of`, `knows_about`, `given_by`, `located_at`,
`leads_to`, `mentions`, `child_map_of`, …). Some types carry semantics the engine understands
(`within` → location hierarchy; `located_at` → NPC placement); the rest are navigation-only.

## 6.3 Context: World Graph

| Aggregate | Contents | Key invariants |
|---|---|---|
| **Entity registry** | id, type, name, article, tags | name unique per (campaign, type) — soft; slug unique per campaign |
| **Location** | extension: location_kind (world/region/country/city/district/building/dungeon/room/poi), population, description fields | containment via `within` links must be acyclic; kind hierarchy advisory, not enforced |
| **NPC** | extension: status, current_location_id (denormalized cache), demeanor, goals, secrets, voice notes; sheet ref | `current_location_id` is a projection of the latest `npc_relocated` event — never edited directly |
| **Faction** | extension: faction_kind, motto, influence | membership via links |
| **Item/Artifact** | extension: rarity, attunement notes; sheet ref | |
| **Map** | extension: image ref, tiling meta, location_id, parent_map | markers/regions are child records, each optionally targeting an entity |
| **MapMarker / MapRegion** | position (pixel coords) / polygon, icon, target entity or free note | deleting target entity nulls the target, keeps the note |

## 6.4 Context: Chronicle (events, timeline, sessions)

- **DomainEvent** — append-only fact: `(id, campaign_id, seq, event_type, occurred_at_game
  (campaign minutes), recorded_at_real, session_id?, actor (gm|time_engine|story_engine|combat),
  payload JSON, narrative_text, subject_entity_ids[])`. The single source of history
  (ADR-004). Event-type catalog in [Event-Sourcing Design](06-event-sourcing.md).
- **TimelineEntry** — curated projection of significant events + manual lore entries
  (pre-campaign history allowed: negative campaign time). Carries display title, icon,
  significance level, and entity references for filtering (FR-8.3).
- **Session** — aggregate for one real-world game session: number, real date, status
  (planned/live/completed), campaign-time span (start/end clock), summary, structured notes
  (decisions, discoveries, loot, XP). While a session is **live**, every domain event is
  stamped with its id — auto-linking (FR-9.3) is then a `GROUP BY` over the session's events.
  Invariant: at most one live session per campaign.

## 6.5 Context: Time Engine

- **CalendarDefinition** — value object (JSON): epoch label, months (name, days), weekdays,
  leap rule, hours/day, seasons, moons. Immutable once the campaign has events (changing
  month lengths would re-date history); superseded by versioning if editing is ever needed.
- **CampaignClock** — one per campaign: `current_time` as **minutes since campaign epoch**
  (single integer; all date math is integer math; formatting is a pure function of clock ×
  calendar). Also stores campaign start offset so "Day N of the campaign" is derivable.
- **ScheduledEvent** — future occurrence: `fire_at_time`, optional recurrence rule
  (interval-based: every N minutes/days/months, or calendar-based: "1st of Flamerule"),
  action descriptor (emit narrative event | change NPC location | change quest status |
  activate story node | custom flag set), `created_by` (gm | npc_schedule | story_engine | quest_deadline).
- **TravelPlan** — transient calculation object (route legs: distance, terrain, pace,
  conveyance) → duration; committing it advances the clock and emits `party_traveled` +
  `party_arrived`.

Invariant: the clock only moves forward through the public `advance_time(to, reason)`
command; it never skips firing due scheduled events (see [Time Engine](07-time-engine.md)).
Backward corrections are compensating adjustments that do not un-fire events.

## 6.6 Context: Playbook (party, quests, encounters, combat)

- **Party** — one per campaign (MVP): member PCs, current_location (projection), gold,
  shared inventory, per-faction reputation scores.
- **PlayerCharacter** — entity extension + rules-system sheet document + per-PC status
  (HP, conditions, resources) maintained by rest/combat commands via the rules plugin.
- **Quest** — extension: quest_type (main/side/hidden), status machine
  `unknown → available → active → completed | failed | expired` (+`abandoned`), giver link,
  reward text/items, deadline (campaign time ⇒ registers a ScheduledEvent), completion
  conditions (checklist), `depends_on` quest links (DAG — cycles rejected).
- **EncounterTemplate** — reusable: monster slots (monster entity + count), NPC participants,
  terrain, environmental effects, hazards, tactics notes, difficulty (computed by plugin
  against current party). Linkable to locations/quests/maps (it's an entity).
- **CombatRun** — one execution of an encounter (or ad-hoc combat): event-sourced action log
  (ADR-005), fold state = initiative order, per-combatant HP/temp HP/conditions/concentration,
  legendary/lair action economy, round counter. Ends by summarizing into domain events and
  advancing the clock.

## 6.7 Context: Story Engine

- **CampaignStateFlag** — `(campaign_id, key, value JSON, updated_by_event)`. The queryable
  "state of the world" (`merchant_alive`, `act`, `dragon_awake`). Written by GM or by
  consequences; every change emits `flag_changed`.
- **StoryNode** — entity extension: narrative description, status
  (`possible → active → resolved | abandoned`), position (graph layout).
- **StoryEdge** — directed: `from_node, to_node, condition (predicate expression over flags &
  quest/NPC statuses), label`. Branching = multiple outgoing edges; merging = multiple incoming.
- **Consequence** — attached to a node's activation/resolution: ordered actions
  (set flag, activate/complete quest, relocate NPC, schedule event, emit narrative event).
- **Trigger** (post-MVP automation, FR-4.5) — subscription: event pattern + condition →
  proposes node activation. MVP evaluates conditions on demand and lets the GM confirm
  ("story suggestions" panel) rather than auto-firing — GM stays the author.

Condition predicates use a small safe expression DSL (comparisons, boolean operators, flag
refs, `quest('id').status`, `npc('id').status`), parsed to an AST — never `eval`.

## 6.8 Context: Rules Engine

See [Rules Engine Architecture](08-rules-engine.md). Domain objects: `RuleSystem` (plugin),
`SheetType` (pc | npc | monster), `StatBlock` (JSON document + schema version),
`ContentPack` (built-in monsters/items shipped by a plugin), `Condition`, `RestRule`,
`TravelPace`, `DifficultyModel`. Core rule: **no other context reads inside a stat-block
document, or inside the live status document derived from it**; they call plugin functions
(`initial_status`, `combat_profile`, `apply_rest`, `encounter_difficulty`, …).

## 6.9 Context: Campaign (accounts & membership)

`User`, `Campaign(rule_system_id, calendar, settings)`, `CampaignMember(user, role ∈ owner |
editor | viewer)`. Every other table carries `campaign_id`; every query is scoped by it
(NFR-6.2). MVP runs with one auto-provisioned local user (ADR-011).

## 6.10 Ubiquitous language (selected)

| Term | Meaning |
|---|---|
| Entity | Any wiki-visible object in the registry |
| Article | The rich-text body of an entity |
| Link / Backlink | Typed directed edge / its reverse view |
| Campaign time | Minutes since campaign calendar epoch (integer) |
| Clock | The campaign's current time value |
| Domain event | Immutable past-tense fact in the log |
| Projection | Table derived from events (timeline, location history) |
| Scheduled event | A future action registered with the time engine |
| Flag | Named campaign-state variable |
| Story node | A potential/actual narrative beat in the story graph |
| Encounter template / Combat run | Reusable design / one execution of it |
| Sheet / Stat block | Rules-system character data document |
| Content pack | Built-in data (monsters, items) shipped by a rules plugin |
