"""Restore the datastore from an automatic backup (docs/13 §7, SECURITY.md).

    python -m scripts.restore_backup            # list available backups
    python -m scripts.restore_backup <id>       # restore that backup

Run this with the server **stopped** — it copies the snapshot's database and media over the
live paths. The most recent state is itself backed up first (reason ``pre-restore``) so a
mistaken restore is undoable.
"""

from __future__ import annotations

import sys

from app.backup import service
from app.core.db import SessionLocal


def _list() -> None:
    backups = service.list_backups()
    if not backups:
        print("no backups found")
        return
    print(f"{'id':40}  {'reason':16}  created")
    for info in backups:
        print(f"{info.id:40}  {info.reason:16}  {info.created_at}")


def main() -> None:
    if len(sys.argv) < 2:
        _list()
        print("\npass a backup id to restore it.")
        return

    backup_id = sys.argv[1]
    # Safety net: snapshot the current state before overwriting it.
    try:
        with SessionLocal() as session:
            saved = service.create_backup(session, reason="pre-restore")
        print(f"current state saved as {saved.id}")
    except service.BackupError as exc:
        print(f"warning: could not snapshot current state ({exc}); continuing")

    info = service.restore_backup(backup_id)
    print(f"restored {info.id} ({info.reason}, {info.media_files} media files)")
    print("start the server to use the restored data.")


if __name__ == "__main__":
    main()
