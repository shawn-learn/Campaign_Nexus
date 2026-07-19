"""Import 5etools content (monsters, items, spells) into a running Campaign_Nexus.

Reads a **local** 5etools data checkout and POSTs converted entries to the live server
over HTTP — same pattern as the ``seed_cos_*`` scripts (the app is installed editable
through a OneDrive junction, so a throwaway process importing the app could bind a
different copy of the database; HTTP guarantees we hit the server's DB).

5etools text is largely copyrighted; nothing is written to the repo — rows land only in
the server's database. ``--srd-only`` restricts to the openly licensed SRD subset.

Usage:
    python scripts/import_5etools.py --type all
    python scripts/import_5etools.py --type monsters --srd-only --sources MM,VGM
    python scripts/import_5etools.py --type items --data "C:/Users/shawn/5etools-src/data"

The converters live in ``app.modules.import5e`` (pure functions, no DB/settings access).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.modules.import5e import codes, copyres, items, legendary, monsters, sources, spells

DEFAULT_DATA = r"C:\Users\shawn\5etools-src\data"
DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_CAMPAIGN = "Curse of Strahd"
SYSTEM_ID = "dnd5e"
BATCH = 200


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class Http:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base}{path}") as r:
            return json.loads(r.read())

    def post(self, path: str, body: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            f"{self.base}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:  # surface validation detail, keep going
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{exc.code} {path}: {detail[:300]}") from exc


# --------------------------------------------------------------------------- #
# Source-file selection
# --------------------------------------------------------------------------- #
def _select_files(dir_path: Path, prefix: str, wanted: set[str] | None) -> list[Path]:
    """Files ``<prefix>-<src>.json`` in ``dir_path``, filtered by the index and ``wanted``."""
    index = sources.load_index(dir_path)  # {"MM": "bestiary-mm.json", ...}
    files: list[Path] = []
    for src, filename in sorted(index.items()):
        if wanted and src.upper() not in wanted:
            continue
        path = dir_path / filename
        if path.exists():
            files.append(path)
    return files


# --------------------------------------------------------------------------- #
# Monsters
# --------------------------------------------------------------------------- #
def import_monsters(http: Http, data: Path, cid: str, args: argparse.Namespace) -> None:
    # High limit: the list endpoint defaults to 200, but a full bestiary is far larger and
    # an incomplete "existing" set would let a re-run create duplicates.
    existing = {m["name"] for m in http.get(f"/api/v1/campaigns/{cid}/monsters?limit=100000")}
    wanted = _parse_sources(args.sources)
    files = _select_files(data / "bestiary", "bestiary", wanted)
    if not files:
        print("  no bestiary files matched")
        return

    # ``_copy`` bases are routinely in a different source file than the variant (CoS
    # creatures copy from MM), so the index must span the whole bestiary even when
    # --sources narrows what we actually convert.
    index = _copy_index(data / "bestiary")
    # Lair actions and regional effects live in their own file, joined by `legendaryGroup`.
    groups = legendary.load_groups(data / "bestiary")

    payload: list[dict[str, Any]] = []
    skipped = converted = 0
    unconvertible: list[str] = []
    # The bestiary keys monsters by name, but 714 names appear in more than one source
    # ("Aboleth" is in both MM and XMM). Without a per-run guard, upgrade mode sends every
    # variant and the last one written wins — so a re-run keeps flip-flopping. Files are
    # iterated in sorted order, so first-wins is deterministic.
    seen_this_run: set[str] = set()
    for path in files:
        entries = sources.load_json(path).get("monster", [])
        for entry in entries:
            name = entry.get("name")
            if not name or name in seen_this_run or (name in existing and not args.upgrade):
                skipped += 1
                continue
            # Licensing is a property of the variant itself, so this must be checked
            # before resolution — otherwise a non-SRD variant inherits its base's srd flag.
            if args.srd_only and not sources.is_srd(entry):
                skipped += 1
                continue
            doc = monsters.to_monster_doc(copyres.resolve_copy(entry, index), groups)
            if doc is None:
                unconvertible.append(name)
                continue
            payload.append({"name": name, "rule_system_id": SYSTEM_ID, "doc": doc})
            existing.add(name)
            seen_this_run.add(name)
            converted += 1
    if args.upgrade:
        # Each entry now carries the whole converted doc; the server merges additively.
        print("  upgrade mode: merging new fields into existing monsters")

    print(f"  converted {converted}, skipped {skipped}, unconvertible {len(unconvertible)}")
    if unconvertible:
        # Naming these matters: silently swallowing them is what hid the ``_copy`` bug,
        # which cost ~1,100 monsters including 79 of the 97 Curse of Strahd creatures.
        shown = ", ".join(sorted(unconvertible)[:20])
        more = f" (+{len(unconvertible) - 20} more)" if len(unconvertible) > 20 else ""
        print(f"    unconvertible: {shown}{more}")
    _flush_monsters(http, cid, payload, args.dry_run, args.upgrade)


def _copy_index(bestiary_dir: Path) -> copyres.MonsterIndex:
    """Index every monster in every bestiary file for ``_copy`` base lookup."""
    entries: list[dict[str, Any]] = []
    for path in sorted(bestiary_dir.glob("bestiary-*.json")):
        entries.extend(sources.load_json(path).get("monster", []))
    return copyres.build_index(entries)


def _flush_monsters(
    http: Http, cid: str, payload: list[dict[str, Any]], dry_run: bool, upgrade: bool = False
) -> None:
    if dry_run:
        verb = "upgrade/import" if upgrade else "import"
        print(f"  [dry-run] would {verb} {len(payload)} monsters")
        return
    imported = upgraded = skipped = 0
    errors: list[str] = []
    body_mode = {"mode": "upgrade"} if upgrade else {}
    for i in range(0, len(payload), BATCH):
        batch = payload[i : i + BATCH]
        result = http.post(
            f"/api/v1/campaigns/{cid}/monsters/import-json", {"monsters": batch, **body_mode}
        )
        imported += result.get("imported", 0)
        upgraded += result.get("upgraded", 0)
        skipped += result.get("skipped", 0)
        errors.extend(result.get("errors", []))
    summary = f"  imported {imported} monsters"
    if upgrade:
        summary += f", upgraded {upgraded}, unchanged {skipped}"
    print(summary + (f", {len(errors)} errors" if errors else ""))
    for err in errors[:10]:
        print(f"    ! {err}")


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #
def import_items(http: Http, data: Path, args: argparse.Namespace) -> None:
    existing = {e["name"] for e in http.get("/api/v1/equipment-library")}
    base_doc = sources.load_json(data / "items-base.json")
    item_dicts = codes.build_item_dicts(base_doc)

    queue: list[dict[str, Any]] = []
    converted = skipped = 0

    def _consider(entry: dict[str, Any], *, is_base: bool) -> None:
        nonlocal converted, skipped
        name = entry.get("name")
        if not name or name in existing:
            return
        if args.srd_only and not sources.is_srd(entry):
            return
        row = items.to_library_entry(entry, item_dicts, source=_item_source(entry), is_base=is_base)
        if row is None:
            return
        queue.append(row)
        existing.add(name)

    for entry in base_doc.get("baseitem", []):
        _consider(entry, is_base=True)
    magic_doc = sources.load_json(data / "items.json")
    for entry in magic_doc.get("item", []):
        _consider(entry, is_base=False)

    if args.dry_run:
        print(f"  [dry-run] would import {len(queue)} library entries")
        return
    for row in queue:
        try:
            http.post("/api/v1/equipment-library", row)
            converted += 1
        except RuntimeError as exc:
            skipped += 1
            if skipped <= 10:
                print(f"    ! {row['name']}: {exc}")
    print(f"  imported {converted} library entries, {skipped} rejected")


def _item_source(entry: dict[str, Any]) -> str:
    """Map a 5etools item to one of the library ``source`` buckets the model allows."""
    # LibraryEntry.source is a free-ish label; use "srd" for SRD, else "custom".
    return "srd" if sources.is_srd(entry) else "custom"


# --------------------------------------------------------------------------- #
# Spells
# --------------------------------------------------------------------------- #
def import_spells(http: Http, data: Path, args: argparse.Namespace) -> None:
    existing = {(s["name"], s.get("source", "")) for s in http.get("/api/v1/spells")}
    class_map: dict[tuple[str, str], list[str]] = {}
    sources_path = data / "spells" / "sources.json"
    if sources_path.exists():
        class_map = spells.load_class_map(sources.load_json(sources_path))

    wanted = _parse_sources(args.sources)
    files = _select_files(data / "spells", "spells", wanted)
    queue: list[dict[str, Any]] = []
    skipped = 0
    for path in files:
        for entry in sources.load_json(path).get("spell", []):
            name = entry.get("name")
            src = entry.get("source", "")
            if not name or (name, src) in existing:
                skipped += 1
                continue
            if args.srd_only and not sources.is_srd(entry):
                skipped += 1
                continue
            classes = class_map.get((name, src))
            row = spells.to_spell(entry, classes=classes)
            if row is None:
                continue
            queue.append(row)
            existing.add((name, src))

    if args.dry_run:
        print(f"  [dry-run] would import {len(queue)} spells (skipped {skipped})")
        return
    imported = rejected = 0
    for row in queue:
        try:
            http.post("/api/v1/spells", row)
            imported += 1
        except RuntimeError as exc:
            rejected += 1
            if rejected <= 10:
                print(f"    ! {row['name']}: {exc}")
    print(f"  imported {imported} spells, {rejected} rejected, {skipped} skipped")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _parse_sources(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _resolve_campaign(http: Http, name: str) -> str:
    campaigns = http.get("/api/v1/campaigns")
    match = next((c for c in campaigns if c["name"] == name), None)
    if match is None:
        raise SystemExit(f"campaign {name!r} not found (have: {[c['name'] for c in campaigns]})")
    return match["id"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Import 5etools content into Campaign_Nexus.")
    parser.add_argument("--type", choices=["monsters", "items", "spells", "all"], default="all")
    parser.add_argument("--base", default=DEFAULT_BASE, help="server base URL")
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN, help="target campaign (monsters)")
    parser.add_argument("--data", default=DEFAULT_DATA, help="path to 5etools data/ dir")
    parser.add_argument("--sources", default=None, help="comma-separated source codes (e.g. MM,PHB)")
    parser.add_argument("--srd-only", action="store_true", help="only import SRD-flagged entries")
    parser.add_argument("--dry-run", action="store_true", help="convert and count, don't POST")
    parser.add_argument("--upgrade", action="store_true",
                        help="merge new fields into existing monsters (monsters only); "
                             "additive — never overwrites hand edits, skips custom/variants")
    args = parser.parse_args(argv)

    data = Path(args.data)
    if not data.exists():
        raise SystemExit(f"data dir not found: {data}")
    http = Http(args.base)

    if args.type in ("monsters", "all"):
        print(f"Monsters -> campaign {args.campaign!r}")
        cid = _resolve_campaign(http, args.campaign)
        import_monsters(http, data, cid, args)
    if args.type in ("items", "all"):
        print("Items -> equipment library (global)")
        import_items(http, data, args)
    if args.type in ("spells", "all"):
        print("Spells -> spell catalog (global)")
        import_spells(http, data, args)


if __name__ == "__main__":
    sys.exit(main())
