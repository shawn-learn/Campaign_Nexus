"""Core: cross-cutting infrastructure shared by every feature module.

Per ADR-001 the core is a *leaf* — it may be imported by feature modules but must
never import them (enforced by import-linter). It owns: configuration, id/time
helpers, the database engine/session, the ORM base + registry, the in-process event
bus, and the command pipeline (`command_tx`) through which every mutation flows.
"""
