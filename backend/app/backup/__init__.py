"""Automatic snapshots of the whole datastore — the SQLite DB and the media tree (FR-13.2).

A backup is a self-contained directory the GM can copy anywhere and restore from without the
app running. It is taken at the moments the data is most likely about to change under it:
before a schema migration, and at the start of a live session. Rotation keeps the newest few.

Backups sit *outside* ``app.modules`` (like ``app.archive``) because they are infrastructure,
not a feature context — they snapshot the raw datastore, not any one module's tables.
"""
