"""Feature modules — each maps to a bounded context (docs/04-domain-model.md).

Modules depend on ``app.core`` and communicate across boundaries via the event bus,
never by importing each other's internals (enforced by import-linter, ADR-001).
"""
