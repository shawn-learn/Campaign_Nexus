"""Campaign archive: full JSON export/import (FR-1.6, NFR-2.5).

A cross-cutting concern that reads and writes every module's campaign-scoped tables, so it
lives outside ``app.modules`` (not bound by the module-layering contracts). Import is a bulk
restore that writes rows directly (like ``rebuild_projections``), not through the event
pipeline — the domain events themselves are part of the archive and restored verbatim.
"""
