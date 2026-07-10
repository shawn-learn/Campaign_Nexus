"""Chronicle context: reads over the domain event log; timeline & sessions later.

The event *table* is core pipeline infrastructure (app.core.domain_event); this module
owns the event-type semantics and, from Sprint 8, the timeline and session aggregates.
"""
