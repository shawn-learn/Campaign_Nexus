# 9. Campaign Time Engine Design

Time is the system's heartbeat: it stamps every event (FR-5.7), drives NPC movement, expires
quests, and fires world events. This document specifies the calendar model, the clock, the
advancement transaction, and the automations built on it.

## 9.1 Calendar model

A **CalendarDefinition** (JSON on `campaign.calendar_json`) describes any fantasy calendar:

```json
{
  "name": "Calendar of Harptos",
  "epoch_label": "DR",
  "minutes_per_hour": 60, "hours_per_day": 24,
  "months": [
    {"name": "Hammer", "days": 30}, {"name": "Midwinter", "days": 1, "festival": true},
    {"name": "Alturiak", "days": 30}, "…"
  ],
  "weekdays": ["First-day", "…10 entries…"],
  "leap": {"every_years": 4, "insert_after_month": "Flamerule", "days": 1, "name": "Shieldmeet"},
  "seasons": [{"name": "Winter", "starts": {"month": "Hammer", "day": 1}}, "…"],
  "moons": [{"name": "Selûne", "cycle_days": 30.4375, "full_at_epoch_offset_days": 15}]
}
```

- Ships with presets: Harptos (Forgotten Realms), Barovian, Exandrian, Gregorian-like
  "Generic Fantasy". Custom calendar *data model* is MVP; the *editor UI* is post-MVP (FR-5.8)
  — early adopters can edit JSON.
- **Immutability rule:** once a campaign has domain events, the calendar is frozen (a change
  would silently re-date all history). Structural fixes require an explicit
  migration command that re-computes affected timestamps — deliberately heavyweight.

## 9.2 The clock

`campaign.clock_time_game` — a single INTEGER: **minutes since calendar epoch**.

- All arithmetic (elapsed days, "3 weeks later", travel durations) is integer math —
  immune to calendar quirks until *formatting*.
- A pure, heavily-tested `CalendarMath` module converts both ways:
  `minutes ⇄ {year, month, day, weekday, time-of-day, season, moon phases}` handling leap
  rules and festival (out-of-week) days.
- Derived displays (days elapsed, week/month/year — FR-5.1) are computed client- and
  server-side from the same conversion spec; the TypeScript port is fixture-tested against
  the Python reference implementation.
- Pre-campaign history uses negative or small values relative to
  `campaign.campaign_start_game` — the timeline renders lore centuries back with the same math.

## 9.3 The advancement transaction (the core algorithm)

`advance_time(campaign, target_time, reason)` — the **only** writer of the clock:

```
assert target_time >= clock
loop:
  due = scheduled_event WHERE status='pending' AND fire_at_game <= target_time
        ORDER BY fire_at_game, id  LIMIT 1
  if none: break
  clock = due.fire_at_game                      # time flows *through* events, in order
  execute(due.action) → mutations + domain events (occurred_at_game = due.fire_at_game)
  emit scheduled_event_fired
  if due.recurrence: schedule next occurrence   # re-enters the queue; may fire again
  else: mark fired
clock = target_time
emit time_advanced(from, to, reason)
COMMIT   # single transaction end-to-end (FR-5.6)
```

Properties worth stating:
- **Ordering:** events fire in chronological order even when one firing schedules another
  inside the window (the loop re-queries) — an NPC itinerary step can chain correctly.
- **Atomicity:** a 30-day downtime jump that fires 40 events is one transaction; the GM never
  sees a half-advanced world (NFR-1.4 budgets this at < 1 s — trivial for SQLite inserts).
- **Runaway guard:** a firing-count ceiling (e.g., 10 000) aborts the transaction with a
  diagnostic — protects against a mis-configured recurrence (every 0 minutes).
- **No backward time.** Corrections are a `time_adjusted` compensating event that moves the
  clock label without re-firing or un-firing anything, plus GM cleanup of consequences.
  Cheap, honest, and avoids the rabbit hole of transactional time reversal.

## 9.4 Advancement sources (FR-5.2)

| Source | Duration | Extra effects |
|---|---|---|
| Manual | GM-chosen ("+3 hours", "to next dawn", absolute) | none |
| Short rest | rules plugin (`5e: 60 min`) | plugin `apply_short_rest` per PC (hit dice, resources) → `short_rest_completed` |
| Long rest | plugin (`5e: 480 min`) | `apply_long_rest` (HP, slots, exhaustion) → `long_rest_completed`; optional random-encounter hook (GM-prompted, post-MVP auto) |
| Travel | computed — §9.5 | `party_traveled`, `party_moved`, arrival triggers |
| Downtime | days × activity | `downtime_spent`; activities catalog post-MVP |
| Waiting | explicit duration | none |
| Combat | `rounds × round_length` (plugin; 5e: 6 s) | applied at combat end (ADR-005) |

## 9.5 Travel calculator (FR-5.3)

Input: an ordered list of legs — `{distance, terrain, pace, conveyance}`.

- **Rates** come from the rules plugin as a `TravelPaceTable`: base speed per pace
  (slow/normal/fast) per conveyance (foot, horse, wagon, ship, flying mount, teleport…),
  terrain multipliers (road ×1, forest ×0.5, mountains ×0.5, swamp ×0.25…), forced-march rules
  as advisory annotations.
- Distances: MVP = GM enters leg distances (optionally reading a ruler measurement from the
  map UI); post-1.0 = stored route distances between linked locations.
- Output: a **TravelPlan preview** (duration, arrival date/time, scheduled events that would
  fire en route — shown *before* committing, so the GM can see "you'd arrive 2 days after the
  festival starts"). Commit = `advance_time(clock + duration, reason=travel)` +
  `party_traveled` + `party_moved(to=destination)`.
- Multi-day travel auto-inserts overnight rest stops as long rests unless the GM opts out
  (forced march).

## 9.6 Scheduled world events (FR-5.5, FR-5.6 examples)

`scheduled_event.action_type` catalog and their handlers:

| action_type | Effect when fired | Typical creator |
|---|---|---|
| `narrate` | emits `world_event` (festival begins, army attacks, crops harvested, season change announcements) | GM, calendar presets |
| `move_npc` | `npc_relocated` (+history projection) | NPC schedules & journeys |
| `set_flag` | `flag_changed` | story engine, GM |
| `quest_status` | e.g. → `expired` at deadline | quest module (auto on deadline set) |
| `activate_story_node` | proposes/activates node per FR-4.4 | story engine |
| `restock_shop` | regenerates a shop inventory (post-MVP; MVP: `narrate` reminder) | GM |

**How actions are wired.** `narrate` and `set_flag` are built into the time module; every
richer action lives in the module that owns its meaning and registers itself via
`scheduled.register_action(action_type, execute=…, describe=…)` at import time (as
`quest_status` does from the playbook). Time never imports upward, so the module-layering
contract holds. `execute` runs *inside* the `advance_time` transaction — it mutates state and
emits events but never commits; `describe` is its read-only twin for the dry-run preview.

Recurrence rules: `{"every": {"days": 7}}` (interval) or
`{"calendar": {"month": "Flamerule", "day": 1}}` (annual festival). Recurring events
re-instantiate on fire (§9.3), so editing a recurrence affects only future occurrences.

**NPC schedules** (FR-6.5) compile to scheduled events lazily: a daily itinerary doesn't
enqueue 365 rows — on each advancement, the engine materializes occurrences of active
`npc_schedule` rules that fall inside the advancement window, then executes them in the same
ordered loop. This keeps the queue small and schedule edits instant.

The compiler is registered from above, like the actions:
`scheduled.register_materializer(materialize=…, preview=…)`. `materialize` runs at the top of
the firing loop (inside the advance tx, no commit) and stamps `materialized_through_game` so
occurrences are compiled exactly once; `preview` reports what *would* be compiled without
writing, so a dry run — and the travel planner's "the world does not wait" panel — still sees
NPC movements that are not in the queue yet.

## 9.7 Interaction with the rest of the system

- **Dashboard** subscribes (post-commit bus) to `time_advanced` → refetches the composite
  dashboard payload (NPCs present, encounters nearby, active quests with deadlines colored by
  urgency).
- **Story engine** re-evaluates suggestion conditions after any advancement (flags and quest
  deadlines are time-sensitive).
- **Session logs** record `clock_start/end`, so "campaign days covered by session 7" — and
  therefore "where was any NPC during session 7" (FR-6.2) — are pure lookups.

## 9.8 Testing focus (see Testing Strategy)

CalendarMath round-trip properties (minutes→date→minutes identity, month-boundary and
leap-day cases); advancement-loop properties (ordering, recurrence chaining, runaway guard,
atomicity under injected mid-loop failure); golden-file tests for Harptos preset dates;
Python↔TypeScript conversion parity fixtures.
