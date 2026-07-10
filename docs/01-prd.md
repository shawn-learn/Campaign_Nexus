# 1. Product Requirements Document (PRD)

**Product:** Campaign Nexus — Dungeon Master Operating System
**Version:** 1.0 (design)
**Date:** 2026-07-07
**Status:** Approved for design

---

## 1.1 Problem Statement

Game Masters running long-form tabletop RPG campaigns juggle information across an ecosystem of
disconnected tools: a wiki or World Anvil for lore, Obsidian or paper notebooks for session notes,
a spreadsheet for the calendar, an encounter builder in one browser tab, a combat tracker in
another, and a PDF library for monster stat blocks.

The consequences are consistent and painful:

- **Duplication and drift.** The same NPC exists in three tools with three contradictory descriptions.
- **Lost history.** Nobody remembers what the party did in session 7, where an NPC was at the
  time, or which shop they robbed. Continuity errors erode player trust in the world.
- **Time is untracked.** Almost no tool treats in-world time seriously, so travel, rests,
  deadlines, festivals, and NPC schedules are hand-waved — and the world feels static.
- **Prep doesn't survive contact with play.** During a live session the GM cannot afford 30
  seconds of searching. If information isn't reachable in one or two clicks, it may as well
  not exist.

## 1.2 Vision

Campaign Nexus is the single system of record for a campaign. It combines:

- the **interconnected articles** of a wiki (World Anvil),
- the **backlinked knowledge graph** of Obsidian,
- the **structured trackers** of encounter builders and combat trackers,
- a **first-class campaign time engine** that no mainstream tool offers,
- and a **live session dashboard** that puts everything relevant to "right now, right here"
  on one screen.

It is explicitly **not** a VTT. There is no fog of war, no token movement, no player-facing view.
Removing the player surface is a strategic choice: it collapses the security model, eliminates
real-time multiplayer complexity, and lets every design decision optimize for one user — the GM.

## 1.3 Goals

| # | Goal | Success signal |
|---|------|----------------|
| G1 | Single source of truth | Any campaign fact exists exactly once; edits propagate everywhere it is referenced |
| G2 | Everything connected | Every entity page shows outbound links **and** automatic backlinks; navigation feels like Wikipedia |
| G3 | Time as a first-class citizen | Travel, rests, and downtime advance a campaign clock that triggers world events |
| G4 | Total recall | "Where was NPC X in session 7?" answerable in one query; full timeline of the campaign |
| G5 | Zero-friction live play | The dashboard answers 90% of in-session lookups without leaving the screen; global search answers the rest in < 1 s |
| G6 | System-agnostic | D&D 5e and Nimble supported at launch; adding a third system requires no schema migration |
| G7 | Built to last | A single developer can maintain and extend it for years; data outlives the app (portable formats, export) |

## 1.4 Non-Goals (explicit)

- Virtual tabletop features: fog of war, line of sight, token movement, player visibility.
- Player accounts or any player-facing surface.
- Real-time multi-user collaborative editing (Google-Docs-style). Sharing between GMs is
  asynchronous (see Security Model).
- Marketplace / publishing of content.
- Mobile-native apps (responsive web is sufficient; tablet is a supported form factor for live play).
- Voice/video, chat, or scheduling of real-world sessions.
- AI features in MVP (see [Future Enhancements](15-future-enhancements.md) — the event log is
  designed so recap generation and timeline summarization can be added without rework).

## 1.5 Product Pillars

1. **The Wiki** — articles for every entity (NPC, location, faction, quest, item…), rich-text
   with `@mentions` that create typed, bidirectional links.
2. **The Clock** — a configurable fantasy calendar and campaign clock; time advancement is a
   transaction that fires scheduled world events.
3. **The Ledger** — an append-only event log of everything that happens; the timeline, NPC
   location history, and party history are projections of it.
4. **The Table** — session tools: live dashboard, encounter builder, combat tracker with
   undo/redo, session logs.
5. **The Engine** — a rules-system plugin layer so no game system is hardcoded.

## 1.6 Competitive Landscape

| Product | Strength we borrow | Gap we fill |
|---------|--------------------|-------------|
| World Anvil | Rich world-building articles, maps with pins | Cluttered UX, weak session-runtime tools, no real time engine |
| Obsidian (+TTRPG plugins) | Backlinks, local-first, speed | Unstructured; no rules data, no combat, no time, assembly required |
| Kanka | Entity relations, campaign focus | No time engine, no story branching, shallow session tools |
| Foundry / Roll20 | Combat tracking, monster data | VTT-first; world knowledge is an afterthought; player-centric |
| LegendKeeper | Fast wiki + maps | No rules data, no combat, no calendar automation |

Campaign Nexus's defensible position is the **integration**: the combat tracker writes to the
same event log the timeline reads; the map pin opens the same NPC article the quest references;
advancing time moves NPCs the wiki describes.

## 1.7 Release Strategy

- **MVP (v0.x):** single GM, local-first deployment (desktop web app served by a local FastAPI
  process against SQLite). See [MVP Definition](16-mvp-definition.md).
- **v1.0:** hardened MVP + second rules system (Nimble) + import/export.
- **Post-1.0:** shared campaigns (co-GM), hosted deployment option, custom calendars UI,
  story-engine automation, AI recap/summarization.

## 1.8 Constraints & Assumptions

- One experienced full-stack developer; no team, no ops staff.
- Stack fixed by mandate: React + TypeScript frontend, FastAPI backend, SQLite storage.
- Data volumes are small by software standards (a huge campaign ≈ tens of thousands of entities,
  hundreds of thousands of events) — well inside SQLite's comfort zone.
- Typical concurrent users per instance: **one** (the GM). Shared campaigns add low-single-digit
  concurrent editors, never real-time.

---

# 2. User Personas

Only GMs use the product, but GMs differ enormously in how they run games. Four personas anchor
every prioritization decision.

## P1 — "The Architect" (primary persona)

- **Profile:** Runs a multi-year homebrew campaign; 10+ years GMing; software-comfortable.
- **Behavior:** Builds world lore months ahead of play. Hundreds of NPCs and locations. Cares
  deeply about consistency and cause-and-effect.
- **Needs:** Knowledge graph, backlinks, timeline, NPC schedules, story branching, custom calendar.
- **Frustration:** "I contradicted my own lore because it was buried in a Google Doc from 2023."
- **Prioritization weight:** Highest. The Architect exercises every subsystem and is the
  design's north star for data-model depth.

## P2 — "The Juggler" (primary persona)

- **Profile:** Runs weekly published-adventure games with light homebrew; prep time is scarce
  (≤ 2 hours/week).
- **Behavior:** Preps the next session only. Lives in the session dashboard and combat tracker.
- **Needs:** Fast entity creation, encounter builder, monster search, initiative tracker,
  session log that mostly writes itself from the event stream.
- **Frustration:** "I don't have time to build a wiki. I need tonight's session to run smoothly."
- **Prioritization weight:** High. The Juggler keeps the product honest about friction — every
  workflow must be usable with minimal upfront investment.

## P3 — "The Historian" (secondary persona)

- **Profile:** Player-turned-GM obsessed with campaign records; writes session recaps for the group.
- **Behavior:** Meticulous session logs, timeline curation, "previously on…" summaries.
- **Needs:** Timeline filtering, session logs with auto-linked entities, search across history,
  (later) AI recap generation.
- **Frustration:** "Reconstructing what happened three sessions ago takes me an hour."

## P4 — "The Collaborator" (secondary, post-MVP)

- **Profile:** Co-GMs a West Marches–style shared world with two other GMs.
- **Behavior:** Multiple GMs run sessions in the same world; needs shared canon with clear
  ownership and change visibility.
- **Needs:** Campaign sharing with roles, edit attribution, eventually change review.
- **Prioritization weight:** Informs the security model and data design now; features ship post-MVP.

## Persona-driven design rules

1. Anything the **Juggler** does weekly must take ≤ 3 clicks from the dashboard.
2. Anything the **Architect** creates must be linkable to anything else.
3. Anything that happens in play must be recorded automatically for the **Historian** — manual
   logging is a supplement, never the primary record.
4. No design decision may paint the **Collaborator** into a corner (e.g., single-user assumptions
   baked into the schema).
