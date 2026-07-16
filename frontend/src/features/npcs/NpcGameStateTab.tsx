import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { Npc } from '../../api/client'
import {
  useNpcHistory,
  useNpcSchedules,
  useSessions,
  useUpdateNpc,
  useDeleteNpcSchedule,
  useCreateNpcSchedule,
  useEntities,
  useItems,
  whereWas,
} from '../../api/hooks'

interface NpcGameStateTabProps {
  campaignId: string
  npc: Npc
}

export function NpcGameStateTab({ campaignId, npc }: NpcGameStateTabProps) {
  const { data: history } = useNpcHistory(campaignId, npc.entity_id)
  const { data: schedules } = useNpcSchedules(campaignId, npc.entity_id)
  const { data: sessions } = useSessions(campaignId)
  const { data: carriedItems } = useItems(campaignId, {
    holder_type: 'npc',
    holder_id: npc.entity_id,
  })
  const [answer, setAnswer] = useState<string | null>(null)

  const askSession = (sessionId: string) => {
    if (!sessionId) return setAnswer(null)
    void whereWas(campaignId, npc.entity_id, { session_id: sessionId })
      .then((res) => {
        const places = res.places.map((p) => p.location_name ?? 'parts unknown')
        setAnswer(places.length ? places.join(' → ') : 'nowhere recorded — they had no location yet')
      })
      .catch((e: Error) => setAnswer(e.message))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* GM notes */}
      <NpcNotes campaignId={campaignId} npc={npc} />

      {/* Where were they */}
      <div className="card">
        <h4 style={{ marginTop: 0 }}>Where were they…</h4>
        <div className="row" style={{ gap: 8 }}>
          <select defaultValue="" onChange={(e) => askSession(e.target.value)}>
            <option value="">— during which session? —</option>
            {sessions?.map((s) => (
              <option key={s.id} value={s.id}>
                Session {s.session_number}
              </option>
            ))}
          </select>
          {answer && <span className="badge">{answer}</span>}
        </div>
      </div>

      {/* Location history */}
      <div className="card">
        <h4 style={{ marginTop: 0 }}>Location history</h4>
        {history?.length === 0 && <p className="muted">Never placed anywhere.</p>}
        <ul className="npc-history">
          {history?.map((row, i) => (
            <li key={i}>
              <span className="mono">{row.from_label}</span>
              <span> → </span>
              <span className="mono">{row.to_label ?? 'now'}</span>
              <strong> {row.location_name ?? 'parts unknown'}</strong>
            </li>
          ))}
        </ul>
      </div>

      {/* Carried Items */}
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <h4 style={{ margin: 0 }}>Carried items</h4>
          <Link
            to="/equipment"
            className="ghost"
            style={{ fontSize: 12, padding: '2px 8px', textDecoration: 'none' }}
          >
            Manage
          </Link>
        </div>
        {!carriedItems?.length && (
          <p className="muted" style={{ margin: 0 }}>This NPC carries nothing.</p>
        )}
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {carriedItems?.map((item) => (
            <li key={item.item_id} className="row" style={{ gap: 6 }}>
              {item.item_type === 'magical' && <span>✨</span>}
              <Link className="linkish" to="/entities/$entityId" params={{ entityId: item.equipment_id }}>
                {item.instance_label ? `${item.equipment_name} · ${item.instance_label}` : item.equipment_name}
              </Link>
              {item.rarity && (
                <span className="badge" style={{ fontSize: 11 }}>
                  {item.rarity.replace('_', ' ')}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* Itinerary */}
      <div className="card">
        <h4 style={{ marginTop: 0 }}>Itinerary</h4>
        <ul className="entities" style={{ marginBottom: 12 }}>
          {schedules?.map((s) => (
            <li key={s.id}>
              <span>
                {s.label || 'Route'}{' '}
                <span className="muted">
                  every {s.interval_days}d · {s.stops.length} stops
                </span>
              </span>
              <ScheduleDelete campaignId={campaignId} scheduleId={s.id} />
            </li>
          ))}
          {schedules?.length === 0 && (
            <p className="muted">No itinerary. Add one and they will move as the clock advances.</p>
          )}
        </ul>
        <NewScheduleForm campaignId={campaignId} npcId={npc.entity_id} />
      </div>
    </div>
  )
}

function NpcNotes({ campaignId, npc }: { campaignId: string; npc: Npc }) {
  const update = useUpdateNpc(campaignId)
  const [goals, setGoals] = useState(npc.goals ?? '')
  const [secrets, setSecrets] = useState(npc.secrets ?? '')
  const [voice, setVoice] = useState(npc.voice_notes ?? '')

  // Re-seed from props when we switch to a different NPC — otherwise the tab
  // component is reused across navigation and keeps the previous NPC's notes.
  useEffect(() => {
    setGoals(npc.goals ?? '')
    setSecrets(npc.secrets ?? '')
    setVoice(npc.voice_notes ?? '')
  }, [npc.entity_id, npc.goals, npc.secrets, npc.voice_notes])

  const dirty =
    goals !== (npc.goals ?? '') ||
    secrets !== (npc.secrets ?? '') ||
    voice !== (npc.voice_notes ?? '')

  const save = () =>
    update.mutate({
      npcId: npc.entity_id,
      goals: goals.trim() || null,
      secrets: secrets.trim() || null,
      voice_notes: voice.trim() || null,
    })

  return (
    <div className="card">
      <h4 style={{ marginTop: 0, marginBottom: 12 }}>GM notes</h4>
      <div className="npc-notes">
        <label className="field">
          <span className="muted">Goals</span>
          <textarea
            rows={2}
            value={goals}
            onChange={(e) => setGoals(e.target.value)}
            placeholder="What are they after?"
          />
        </label>
        <label className="field">
          <span className="muted">Secrets</span>
          <textarea
            rows={2}
            value={secrets}
            onChange={(e) => setSecrets(e.target.value)}
            placeholder="What are they hiding?"
          />
        </label>
        <label className="field">
          <span className="muted">Voice / mannerisms</span>
          <textarea
            rows={2}
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            placeholder="How do they sound?"
          />
        </label>
        <button onClick={save} disabled={!dirty || update.isPending}>
          {update.isPending ? 'Saving…' : 'Save notes'}
        </button>
      </div>
    </div>
  )
}

function ScheduleDelete({ campaignId, scheduleId }: { campaignId: string; scheduleId: string }) {
  const del = useDeleteNpcSchedule(campaignId)
  return (
    <button className="ghost tag-x" onClick={() => del.mutate(scheduleId)}>
      ×
    </button>
  )
}

function NewScheduleForm({ campaignId, npcId }: { campaignId: string; npcId: string }) {
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const create = useCreateNpcSchedule(campaignId)
  const [label, setLabel] = useState('Daily round')
  const [stops, setStops] = useState<{ hour: string; location_id: string }[]>([
    { hour: '8', location_id: '' },
  ])

  const ready = stops.every((s) => s.location_id) && stops.length > 0

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!ready) return
        create.mutate({
          npcId,
          label,
          interval_days: 1,
          stops: stops.map((s) => ({
            at_seconds: Math.round(Number(s.hour) * 3600),
            location_id: s.location_id,
          })),
        })
      }}
    >
      <div className="row" style={{ gap: 6, marginBottom: 6 }}>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" />
        <button
          type="button"
          className="ghost"
          onClick={() => setStops((s) => [...s, { hour: '18', location_id: '' }])}
        >
          + stop
        </button>
      </div>
      {stops.map((stop, i) => (
        <div key={i} className="row" style={{ gap: 6, marginBottom: 4 }}>
          <input
            style={{ width: 60 }}
            value={stop.hour}
            aria-label="hour of day"
            onChange={(e) =>
              setStops((s) => s.map((x, j) => (j === i ? { ...x, hour: e.target.value } : x)))
            }
          />
          <span className="muted">:00 →</span>
          <select
            value={stop.location_id}
            onChange={(e) =>
              setStops((s) =>
                s.map((x, j) => (j === i ? { ...x, location_id: e.target.value } : x)),
              )
            }
          >
            <option value="">— where? —</option>
            {locations?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </div>
      ))}
      <button type="submit" disabled={!ready || create.isPending} style={{ marginTop: 6 }}>
        Save itinerary
      </button>
    </form>
  )
}
