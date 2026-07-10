# 11. UI Architecture & 12. Navigation Model

Stack per ADR-007/008/009: Vite · React 18 · TypeScript strict · TanStack Query & Router ·
Zustand · Tiptap · React Flow · Leaflet.

---

## 11.1 Application shell

```
┌──────────────────────────────────────────────────────────────────────┐
│ Top bar: campaign switcher · clock widget (date/time + advance ▾) ·  │
│          ⌘K search · session status chip (● LIVE / start session)    │
├───────────┬──────────────────────────────────────────┬───────────────┤
│ Left nav  │                Main view                 │  Side panel   │
│ Dashboard │   (routed content: entity page, map,     │  (contextual: │
│ World     │    timeline, quest board, combat, …)     │   entity peek,│
│ NPCs      │                                          │   backlinks,  │
│ Factions  │                                          │   quick notes)│
│ Quests    │                                          │               │
│ Encounters│                                          │               │
│ Monsters  │                                          │               │
│ Maps      │                                          │               │
│ Timeline  │                                          │               │
│ Sessions  │                                          │               │
│ Story     │                                          │               │
└───────────┴──────────────────────────────────────────┴───────────────┘
```

Three persistent affordances implement the two-click rule (NFR-3.1):

1. **⌘K command palette** — global search (FR-13) + commands ("advance time", "start
   session", "new NPC"). One keystroke from anywhere.
2. **Clock widget** — always visible; dropdown exposes every advancement source (manual,
   rest, travel, wait) with a preview of events that will fire (§9.5 of the Time Engine).
3. **Side panel (entity peek)** — clicking any entity reference anywhere opens a compact
   article view in the panel *without navigating away*. A second click ("expand") commits to
   full-page navigation. This is what makes the dashboard and maps usable mid-session.

## 11.2 Frontend module structure (mirrors backend modules)

```
src/
  api/            generated OpenAPI client + TanStack Query hooks per resource
  shell/          layout, nav, command palette, clock widget, theming (dark mode default)
  features/
    dashboard/    live session dashboard (panel grid)
    wiki/         entity pages, article editor (Tiptap), backlinks, relation editor
    graph/        entity-neighborhood view, story graph editor, quest DAG (React Flow)
    maps/         Leaflet viewer/editor, marker & region tools, breadcrumb stack
    time/         calendar views, advancement dialogs, travel planner
    timeline/     timeline browser + filters
    sessions/     session list, live session controls, session log composer
    quests/       quest board (kanban by status), quest page widgets
    combat/       encounter builder, combat tracker (reducer + optimistic UI)
    rules/        stat-block renderers (generic + per-system registry), monster browser
  stores/         Zustand: combat UI state, dashboard layout, palette state
  lib/            calendar-math (TS port), combat reducer (TS twin), dice, mention utils
```

State discipline: **server state only in TanStack Query** (normalized by resource key,
invalidated by mutation → satisfies FR-14.3); **client state only in Zustand** (nothing
fetched ever lives in Zustand). The generated API client makes drift between backend and
frontend types a compile error (NFR-4.3).

## 11.3 Key screens

- **Entity page (the wiki workhorse).** Header (name, type, tags, portrait) · structured
  fields (type-specific form) · article (Tiptap; `@mention` inserts entity nodes) ·
  **Relations** editor (typed links) · **Referenced by** (backlinks, grouped by type) ·
  **History** (this entity's timeline slice, from `event_entity`) · type-specific widgets
  (NPC: location history + schedule; Quest: objectives, dependencies mini-DAG; Location:
  contents tree, residents, maps; Monster: stat block).
- **Live dashboard (FR-14).** A fixed grid of panels — clock+advance · party status · active
  quests (deadline-sorted) · NPCs at current location · encounters here/nearby · current map
  (mini) · initiative tracker (embedded combat view) · pinned stat blocks · quick notes
  (append-only stream → `note_captured` events) · recent events feed. Panels deep-link via
  entity peek. Layout presets: *Prep* / *Exploration* / *Combat* (combat swaps the map panel
  for the full tracker).
- **Combat tracker.** Initiative rail (drag to reorder), combatant cards (HP bar, temp HP,
  conditions as icon chips, concentration flag, legendary/lair counters), round/turn header,
  damage-entry keypad optimized for keyboard (`enter number ⏎`), undo/redo buttons + history
  scrubber. All actions optimistic via the TS reducer twin (NFR-1.3), reconciled with server.
- **Map viewer/editor.** Leaflet CRS.Simple + tile pyramid; marker palette by entity type;
  edit mode vs. play mode; clicking a marker → entity peek; child-map markers push onto a
  **map breadcrumb stack** (world ▸ region ▸ city) for instant back-navigation (FR-3.4).
- **Timeline.** Vertical stream grouped by campaign date, significance-scaled markers,
  filter bar (session/NPC/quest/location/faction/date/type), infinite scroll windowed on
  `occurred_at_game`.
- **Story graph.** React Flow canvas; nodes colored by status; edge labels show conditions;
  a **Suggestions** drawer lists nodes whose conditions currently evaluate true (GM confirms
  activation — FR-4.4).
- **Quest board.** Kanban by status + DAG view toggle (React Flow + dagre).

## 11.4 Design system

- Tailwind CSS + Radix UI primitives (accessible dialogs/menus/popovers) + a thin bespoke
  component kit ("parchment-dark" theme; dark mode is the default per NFR-3.4).
- Iconography: one set (Lucide) + entity-type color coding used consistently in search
  results, links, map markers, and graph nodes — the type-color is the user's subconscious
  wayfinding system.
- Responsive to tablet (NFR-3.3): left nav collapses to icons; side panel becomes an overlay;
  dashboard grid reflows to two columns. No phone layout in scope.

---

# 12. Navigation Model

## 12.1 Principles

1. **Wiki-first:** every noun on screen is a link. Links never dead-end — a red "missing"
   mention offers *create entity here* (Obsidian's killer loop).
2. **Peek, then commit:** first click = side-panel peek; explicit second action = navigate.
   Mid-session, the GM never loses the dashboard by being curious.
3. **Hub-and-spoke hubs** are the left-nav index pages (filterable tables); spokes are entity
   pages; **lateral movement** is links/backlinks — Wikipedia-style browsing (G2).
4. **Search is navigation:** ⌘K is expected to be the most-used control in the app; it must
   stay under 100 ms (NFR-1.2).

## 12.2 Route map (TanStack Router, type-safe params)

```
/campaigns                         campaign switcher
/c/:campaign/dashboard             live dashboard (default route)
/c/:campaign/w/:slug               ANY entity page (registry-routed by slug;
                                   type-specific page component chosen at render)
/c/:campaign/browse/:type          index hubs (npc, location, quest, monster, …)
/c/:campaign/map/:slug             map viewer (marker/region deep-link via ?focus=)
/c/:campaign/timeline              timeline (+ ?filters)
/c/:campaign/sessions/:num         session page
/c/:campaign/story                 story graph
/c/:campaign/combat/:runId         combat tracker (also embedded in dashboard)
/c/:campaign/settings              calendar, rules system, members, export
```

One generic entity route (`/w/:slug`) is deliberate: new entity types get pages without new
routes, and every internal link is constructible from `(campaign, slug)` alone.

## 12.3 Wayfinding aids

- **Breadcrumbs** on entity pages follow the `within` chain (Barrow Tavern ‹ Duskmere ‹
  The Reach ‹ Aerith). On maps, the breadcrumb is the map stack.
- **Back/forward** are first-class (router history), including peek-panel history.
- **Recently viewed** (last 20 entities) in the palette's empty state.
- **Pinning:** any entity can be pinned to the current session; pins appear on the dashboard.

## 12.4 Editing model

In-place editing everywhere (fields commit on blur; article autosaves drafts every few
seconds with explicit *save* creating the audit event). No modal "edit mode" — the wiki must
feel as fast to write as to read, or the Juggler persona won't feed it.
