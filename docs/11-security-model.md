# 14. Security Model

Context that shapes everything: the app is **GM-only** (no player surface — the classic VTT
problem of hiding secrets from players *inside* the app does not exist), and the MVP is
**local-first single-user** (ADR-011). The model is therefore deliberately small now, with
the seams for multi-GM sharing built in from day one.

## 14.1 Deployment postures

| Posture | When | Exposure |
|---|---|---|
| **P-Local (MVP)** | GM's own machine | binds `127.0.0.1` only; auto-provisioned local user; auth middleware present but in trusted single-user mode |
| **P-LAN** | GM hosts for co-GMs on a network / reverse proxy | full auth enforced; TLS via user's proxy (documented recipe, e.g. Caddy) |
| **P-Hosted (post-1.0)** | managed multi-tenant | full auth + hardening + PostgreSQL port; out of MVP scope but nothing may preclude it |

The codebase always runs the same authorization pipeline; P-Local simply short-circuits
*authentication* to the local user. There is no "security added later" — only *login* added
later. This is the cheap insurance that makes ADR-011's deferral safe.

## 14.2 Authentication

- Session-cookie authentication (HttpOnly, SameSite=Lax, Secure under TLS) with server-side
  session store; CSRF token (double-submit) on mutating requests. Chosen over JWT: sessions
  are revocable, and there are no third-party API consumers to serve (ADR-006) — stateless
  tokens solve a problem we don't have.
- Passwords: argon2id. No OAuth in MVP scope; email+password only when auth activates (P-LAN).
- Rate limiting on auth endpoints (slowapi) from the moment login exists.

## 14.3 Authorization

- **Every** data row belongs to a campaign; **every** query and command is scoped by
  `campaign_id` derived from the URL path and checked against `campaign_member` (NFR-6.2).
  The check lives in one FastAPI dependency (`require_campaign_role(role)`) — no per-endpoint
  reinvention, no unscoped code path to audit.
- Roles (FR-1.5): `owner` (everything incl. sharing, delete, export), `editor` (all content
  operations), `viewer` (read-only — a co-GM reading lore between sessions).
- Object-level nuance is intentionally absent: within a campaign, GM trust is all-or-nothing.
  (Per-entity ACLs are a complexity trap with no persona demanding them.)
- Cross-campaign references are rejected at the service layer (an entity may only link to
  entities of the same campaign) — this is both a domain invariant and the tenant-isolation
  guarantee.

## 14.4 Input & content safety

- All input validated by Pydantic at the boundary; SQL exclusively via SQLAlchemy bound
  parameters (no string SQL); path traversal impossible for media (content-addressed
  filenames under a fixed root, no user-supplied paths).
- **Rich text:** stored as Tiptap JSON, rendered by React components from a whitelisted node
  schema — unknown nodes/attributes are dropped on save and ignored on render. No
  `dangerouslySetInnerHTML` anywhere; article HTML export sanitizes via allowlist.
- **Uploads:** MIME sniffing (magic bytes, not extension), size caps (configurable, default
  50 MB maps / 10 MB portraits), image re-encode on tiling (strips embedded payloads/EXIF);
  served with `Content-Disposition` + `X-Content-Type-Options: nosniff` from a cookie-less path.
- **Condition DSL** (story engine): parsed to a closed AST (comparisons, boolean ops,
  whitelisted accessors), evaluated by a tree-walker with step limits. Never `eval`. Same for
  scheduled-event `action_json`: a closed catalog of action types, each with a Pydantic
  payload — no arbitrary code in data.
- **Rules plugins are code, not content**: installed by the operator like any Python package
  (same trust level as the app itself); campaign *data* can never carry executable behavior.
  A community-plugin marketplace, if ever, is a post-1.0 problem explicitly out of scope.

## 14.5 Data protection

- Threat model honesty: SQLite file and media folder are plaintext on the GM's disk; at-rest
  encryption is delegated to OS disk encryption (documented). The realistic top threat to
  this data is not exfiltration — it's **loss**; hence backups are a security control
  (NFR-2.2): rotating timed copies + pre-migration + on-session-start snapshots, plus
  one-click export (NFR-2.5).
- Backups/exports contain everything (secrets included) — export UI labels them accordingly.
- Logs never contain article content or secrets; only ids and event types.

## 14.6 Sharing model (post-1.0 design sketch, so nothing forecloses it)

- Invite by email → `campaign_member` row with role; owner can change/revoke.
- Attribution: `created_by`/`updated_by` on entities and events (already in schema).
- Concurrency: optimistic versioning (`expected_version`, §13.1) + SSE change feed (§13.4);
  last-write-wins with conflict surfacing, not real-time merge (non-goal per PRD 1.4).
- The domain event log doubles as the audit trail of *who changed the world and when*.

## 14.7 Security checklist per release

Dependency audit (`pip-audit`, `npm audit`) in CI · CSP (`default-src 'self'`) even in
P-Local · secrets (session key) generated on first run, stored outside the DB ·
`SECURITY.md` with the posture matrix and hardening recipe for P-LAN.
