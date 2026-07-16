import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useCaptureNote,
  useDashboard,
  useEntities,
  useSetDashboardLocation,
  useSetDashboardPin,
} from '../../api/hooks'
import { CalendarMath } from '../../lib/calendar'
import type { CalendarDef } from '../../lib/calendar'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import type { Dashboard, EntityBrief, QuestBrief } from '../../api/client'

// The live session dashboard (FR-14, the MVP gate): one composite read (GET /views/dashboard)
// rendered as a reflowing panel grid. Layout presets shift which panels are emphasized so the
// GM can run prep, exploration, and combat from the same screen without navigating away.
type Preset = 'prep' | 'exploration' | 'combat'

export function DashboardPage() {
  const { campaign, isLoading } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data, isLoading: dashLoading } = useDashboard(campaignId)
  const [preset, setPreset] = useState<Preset>('exploration')

  if (isLoading || dashLoading) return <p className="muted">Loading dashboard…</p>
  if (!campaign || !data) return <p className="muted">Select a campaign to begin.</p>

  // Combat preset promotes the tracker; when combat is live, snap to it automatically.
  const effective: Preset = data.active_combat ? 'combat' : preset

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 14 }}>
        <div className="row" style={{ gap: 10 }}>
          <h2 style={{ margin: 0 }}>{campaign.name}</h2>
          {data.session ? (
            <span className="badge">
              Session {data.session.session_number} · {data.session.status}
            </span>
          ) : (
            <span className="muted" style={{ fontSize: 13 }}>No live session</span>
          )}
        </div>
        <div className="dash-presets">
          {(['prep', 'exploration', 'combat'] as const).map((p) => (
            <button
              key={p}
              className={effective === p ? 'active' : 'ghost'}
              onClick={() => setPreset(p)}
            >
              {p[0].toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="dash-grid">
        <ClockPanel clock={data.clock} />
        {effective === 'combat' && <CombatPanel combat={data.active_combat} />}
        <LocationPanel campaignId={campaign.id} data={data} />
        <PartyPanel data={data} />
        {effective !== 'combat' && <QuestsPanel quests={data.active_quests} />}
        <PinnedPanel campaignId={campaign.id} pinned={data.pinned} />
        <NotesPanel campaignId={campaign.id} notes={data.notes} />
        <EventsPanel events={data.recent_events} />
      </div>
    </>
  )
}

function EntityLink({ e }: { e: EntityBrief }) {
  return (
    <Link className="linkish" to="/entities/$entityId" params={{ entityId: e.id }}>
      {e.name}
    </Link>
  )
}

function ClockPanel({ clock }: { clock: Dashboard['clock'] }) {
  const cal = useMemo(
    () => new CalendarMath(clock.calendar as unknown as CalendarDef),
    [clock.calendar],
  )
  const f = cal.format(clock.time_game)
  return (
    <div className="dash-panel">
      <h4>
        Clock
        {clock.realtime_paused && <span className="tag danger">⚔ combat</span>}
        {!clock.realtime_paused && clock.realtime_enabled && <span className="tag">live</span>}
      </h4>
      <div className="dash-clock-time">{f.time}</div>
      <div className="muted" style={{ fontSize: 13 }}>
        {f.weekday}, {f.day} {f.month} {f.year}
        {f.season ? ` · ${f.season}` : ''}
      </div>
    </div>
  )
}

function PartyPanel({ data }: { data: Dashboard }) {
  const { party } = data
  return (
    <div className="dash-panel">
      <h4>
        <span>Party</span>
        <span className="muted">🪙 {party.wealth_label}</span>
      </h4>
      {party.members.length === 0 && <div className="dash-empty">No party members yet.</div>}
      <ul>
        {/* hp/max_hp are the plugin's reading of its own status shape — see PartyMemberOut. */}
        {party.members.map((m) => (
          <li key={m.stat_block_id}>
            <span>{m.name}</span>
            <span className="badge">{m.hp} / {m.max_hp} hp</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Deadlines are coloured by urgency at a glance (docs/07 §9.7): an overdue quest is one the
// clock has already passed — it will expire the moment time is advanced through it.
function QuestsPanel({ quests }: { quests: QuestBrief[] }) {
  return (
    <div className="dash-panel">
      <h4>Active quests</h4>
      {quests.length === 0 && <div className="dash-empty">No active quests.</div>}
      <ul>
        {quests.map((q) => (
          <li key={q.id}>
            <EntityLink e={q} />
            <span className="row" style={{ gap: 6 }}>
              {q.deadline_label && (
                <span className={'badge' + (q.overdue ? ' diff-deadly' : '')}>
                  ⌛ {q.deadline_label}
                </span>
              )}
              <span className={`badge quest-${q.status}`}>{q.status}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function LocationPanel({ campaignId, data }: { campaignId: string; data: Dashboard }) {
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const setLocation = useSetDashboardLocation(campaignId)
  const here = data.current_location
  return (
    <div className="dash-panel span-2">
      <h4>
        <span>Current location</span>
        <select
          value={here?.id ?? ''}
          onChange={(e) => setLocation.mutate(e.target.value || null)}
          aria-label="Set current location"
        >
          <option value="">— none —</option>
          {locations?.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </h4>
      {!here && (
        <div className="dash-empty">Pick where the party is to see who and what is here.</div>
      )}
      {here && (
        <div className="link-panels">
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>NPCs here</div>
            {data.npcs_here.length === 0 && <div className="dash-empty">Nobody around.</div>}
            <ul>
              {data.npcs_here.map((n) => <li key={n.id}><EntityLink e={n} /></li>)}
            </ul>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Encounters here</div>
            {data.encounters_here.length === 0 && <div className="dash-empty">None staged.</div>}
            <ul>
              {data.encounters_here.map((n) => <li key={n.id}><EntityLink e={n} /></li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

function PinnedPanel({ campaignId, pinned }: { campaignId: string; pinned: EntityBrief[] }) {
  const setPin = useSetDashboardPin(campaignId)
  return (
    <div className="dash-panel">
      <h4>Pinned</h4>
      {pinned.length === 0 && (
        <div className="dash-empty">Pin NPCs, quests, or stat blocks for quick reference.</div>
      )}
      <ul>
        {pinned.map((p) => (
          <li key={p.id}>
            <EntityLink e={p} />
            <button
              className="pin-x"
              title="Unpin"
              onClick={() => setPin.mutate({ entityId: p.id, pinned: false })}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function NotesPanel({ campaignId, notes }: { campaignId: string; notes: Dashboard['notes'] }) {
  const capture = useCaptureNote(campaignId)
  const [text, setText] = useState('')
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    capture.mutate(text.trim(), { onSuccess: () => setText('') })
  }
  return (
    <div className="dash-panel">
      <h4>Quick notes</h4>
      <form className="row" onSubmit={submit} style={{ marginBottom: 8 }}>
        <input
          style={{ flex: 1 }}
          placeholder="Jot a note…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" disabled={capture.isPending}>Add</button>
      </form>
      {notes.length === 0 && <div className="dash-empty">No notes captured yet.</div>}
      <ul className="feed">
        {notes.map((n) => (
          <li key={n.id}><span>{n.narrative}</span></li>
        ))}
      </ul>
    </div>
  )
}

function EventsPanel({ events }: { events: Dashboard['recent_events'] }) {
  return (
    <div className="dash-panel span-2">
      <h4>Recent events</h4>
      {events.length === 0 && <div className="dash-empty">No events yet.</div>}
      <ul className="feed">
        {events.map((e) => (
          <li key={e.id}>
            <span className="badge">{e.event_type}</span>
            <span>{e.narrative}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function CombatPanel({ combat }: { combat: Dashboard['active_combat'] }) {
  if (!combat) {
    return (
      <div className="dash-panel">
        <h4>Combat</h4>
        <div className="dash-empty">No combat running. Start one from the Combat tab.</div>
      </div>
    )
  }
  const { state } = combat
  const active = state.order[state.turn_index]
  return (
    <div className="dash-panel span-2">
      <h4>
        <span>Combat · round {state.round}</span>
        <Link className="linkish" to="/combat">Open tracker →</Link>
      </h4>
      <ul>
        {state.order.map((id) => {
          const c = state.combatants[id]
          if (!c) return null
          return (
            <li key={id} style={{ opacity: c.defeated ? 0.5 : 1 }}>
              <span>
                {id === active ? '▶ ' : ''}{c.name}
                {c.concentrating ? ' ⊙' : ''}
              </span>
              <span className="badge">{c.hp}/{c.max_hp} hp</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
