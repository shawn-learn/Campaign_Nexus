# Campaign Nexus — Dungeon Master Operating System

A web application that serves as a Game Master's central operating system: world-building wiki,
knowledge graph, campaign time engine, session runner, encounter builder, and combat tracker —
in one interconnected, searchable, historically-tracked system.

**This is not a VTT.** Players never touch it. It exists to make one person — the GM — faster,
more organized, and more consistent.

> Design philosophy: every piece of campaign information exists exactly once, is interconnected,
> searchable, historically tracked, and accessible within one or two clicks.

## Status

Design phase. No implementation code yet. This repository currently contains the complete
software development plan.

## Document Index

| # | Document | Covers |
|---|----------|--------|
| 1 | [Product Requirements Document](docs/01-prd.md) | Vision, goals, personas, scope |
| 2 | [Requirements](docs/02-requirements.md) | Functional & non-functional requirements |
| 3 | [Architecture Decision Records](docs/03-adr.md) | All major technical decisions, with justification |
| 4 | [Domain Model](docs/04-domain-model.md) | Bounded contexts, entities, aggregates, invariants |
| 5 | [Database Schema](docs/05-database-schema.md) | Full SQLite schema (DDL), indexing, FTS |
| 6 | [Event-Sourcing Design](docs/06-event-sourcing.md) | Hybrid event log, projections, combat undo/redo |
| 7 | [Campaign Time Engine](docs/07-time-engine.md) | Calendars, clock, travel, rests, scheduled events |
| 8 | [Rules Engine Architecture](docs/08-rules-engine.md) | System-agnostic plugin design; D&D 5e & Nimble |
| 9 | [UI Architecture & Navigation Model](docs/09-ui-architecture.md) | Frontend stack, layout, navigation, live dashboard |
| 10 | [API Design](docs/10-api-design.md) | REST resource model, composite endpoints, conventions |
| 11 | [Security Model](docs/11-security-model.md) | AuthN/AuthZ, sharing, threat model |
| 12 | [Development Roadmap & Sprint Plan](docs/12-roadmap.md) | Phases, sprint-by-sprint plan |
| 13 | [Risk Register](docs/13-risk-register.md) | Ranked risks with mitigations |
| 14 | [Testing Strategy](docs/14-testing-strategy.md) | Test pyramid, engine test suites, tooling |
| 15 | [Future Enhancements](docs/15-future-enhancements.md) | Post-1.0 features incl. AI roadmap |
| 16 | [MVP Definition & Milestones](docs/16-mvp-definition.md) | Single-developer MVP, milestones, effort, deferrals |

## Technology Summary (see ADRs for justification)

- **Architecture:** modular monolith (FastAPI), hybrid event log (not pure event sourcing), lightweight CQRS read models
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- **Database:** SQLite (WAL mode, FTS5, JSON1) — schema kept PostgreSQL-portable
- **Knowledge graph:** typed edge table in SQLite + recursive CTEs (no separate graph database)
- **API:** REST + composite read endpoints (no GraphQL)
- **Frontend:** React 18 + TypeScript, Vite, TanStack Query & Router, Zustand, Tiptap editor
- **Graphs:** React Flow (story graph, quest dependencies) · **Maps:** Leaflet with `CRS.Simple`
- **Rules systems:** plugin architecture; ships with D&D 5e, validated by a second system (Nimble)
