"""Equipment module — item catalog + ownership tracking (docs/04, §6.X).

Two tiers: an ``Equipment`` *definition* (a wiki ``Entity`` of type
``"equipment"`` carrying GM-authored fields — type, rarity, properties) and its
individual ``Item`` *copies*, each independently held and located.  All
ownership changes flow through the event log so the full provenance timeline is
always recoverable.
"""
