# Security & Operations

Campaign Nexus is a **GM-only, local-first** application: one game master runs it on their own
machine, and there is no player-facing surface. The full model lives in
[`docs/11-security-model.md`](docs/11-security-model.md); this file is the operator's quick
reference — deployment postures, the LAN-hardening recipe, and the backup/restore runbook.

## Reporting a vulnerability

This is a solo, local-first project. If you find a security issue, open a private report by
emailing the maintainer (see the repo owner) rather than filing a public issue. Because the
default posture binds to `localhost` only, most issues require an already-compromised machine
to exploit; please note the posture you tested against.

## Deployment postures

| Posture | When | Exposure |
|---|---|---|
| **P-Local** (default) | Your own machine | Binds `127.0.0.1` only; the local user is auto-provisioned; the auth pipeline runs but authentication is short-circuited to that single user. |
| **P-LAN** | Hosting for co-GMs over a LAN | Full authentication enforced; TLS terminated by a reverse proxy you run (recipe below). |
| **P-Hosted** | Managed multi-tenant | Out of MVP scope; nothing in the codebase precludes it (Postgres port + full auth). |

The same authorization pipeline runs in every posture — `require_campaign_role(...)` scopes
every query by `campaign_id`. Moving from P-Local to P-LAN turns on *login*, not *security*.

### Staying in P-Local safely
- Leave `NEXUS_HOST=127.0.0.1` (the default). Do **not** bind `0.0.0.0` without a proxy.
- The SQLite database and the `media/` and `backups/` folders are **plaintext on disk**.
  At-rest protection is delegated to your OS disk encryption (FileVault / BitLocker / LUKS).
- Exports and backups contain **everything, including any secrets you wrote into articles**.
  Treat an exported `.json` archive like the database itself.

### Hardening recipe for P-LAN (reverse proxy + TLS)
Run the app bound to localhost and put a TLS-terminating proxy in front. Example with
[Caddy](https://caddyserver.com), which gets you automatic HTTPS:

```
# Caddyfile
nexus.example.internal {
    reverse_proxy 127.0.0.1:8000
}
```

Then start the backend as usual (it stays on `127.0.0.1:8000`); Caddy handles TLS and is the
only process listening on the network. Before exposing it:
- Ensure authentication is enabled (P-LAN mode) so co-GMs log in.
- Keep the proxy and the app on the same host, or use an encrypted tunnel (WireGuard /
  Tailscale) rather than exposing the port to an untrusted network.
- Run the dependency audit (`pip-audit`, `npm audit`) and apply updates before going live.

## Backups & restore (the data-loss control)

The realistic top threat to a campaign is **loss**, not exfiltration — so backups are treated
as a security control. A backup is a self-contained directory under `backups/` holding a
consistent copy of the database (`campaign_nexus.db`, taken with SQLite `VACUUM INTO` so it is
safe even mid-session), the whole `media/` tree, and a `manifest.json`.

**Automatic snapshots** are taken at the two moments the data is most at risk:
- **before a schema migration** (reason `pre-migration`), at startup when the DB is behind head;
- **at the start of a live session** (reason `session-start`).

Rotation keeps the newest `NEXUS_BACKUP_KEEP` backups (default 10). You can also take one on
demand:

```
POST /api/v1/backups            # {"reason": "before big edit"}
GET  /api/v1/backups            # list, newest first
```

### Restoring (target: under 2 minutes)
Restore overwrites the live database and media, so **stop the server first**, then:

```
# 1. Stop the running app (Ctrl-C on `python start.py`).
cd backend

# 2. See what's available.
uv run python -m scripts.restore_backup

# 3. Restore one by id. The current state is snapshotted first (reason `pre-restore`),
#    so a mistaken restore is itself undoable.
uv run python -m scripts.restore_backup 20260710T120000Z_session-start

# 4. Start the app again.
cd .. && python start.py
```

The restore copies the snapshot's `campaign_nexus.db` and `media/` over the live paths and
clears any stale SQLite `-wal`/`-shm` sidecars. A full JSON export/import
(`GET /api/v1/campaigns/{id}/export`) is the portable alternative when you want to move a single
campaign to another machine rather than roll the whole datastore back.

## Input & content safety (summary)

- All input is validated by Pydantic at the boundary; SQL is exclusively via SQLAlchemy bound
  parameters. Uploaded media is MIME-sniffed by magic bytes and stored content-addressed under
  a fixed root — user input never influences a filesystem path.
- Rich text is stored as Tiptap JSON and rendered by React from a whitelisted node schema; no
  `dangerouslySetInnerHTML` anywhere.
- Scheduled-event actions and (from Sprint 20) story-graph conditions are a **closed catalog /
  parsed AST**, never `eval` — campaign *data* can never carry executable behaviour.
