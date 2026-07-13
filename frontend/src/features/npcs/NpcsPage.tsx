import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useCreateNpc,
  useCreateNpcSchedule,
  useDeleteNpcSchedule,
  useEntities,
  useNpcHistory,
  useNpcSchedules,
  useNpcs,
  useRecordInteraction,
  useRelocateNpc,
  useSessions,
  useSetNpcStatus,
  whereWas,
} from '../../api/hooks'
import type { NpcFilters } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import type { Npc } from '../../api/client'

const STATUSES = ['alive', 'dead', 'missing', 'unknown', 'retired'] as const

// NPC dynamics (FR-6): the saved queries the spec asks for, an NPC's location history as a
// derived timeline, and the itinerary editor whose rules the clock compiles as it advances.
export function NpcsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const [filters, setFilters] = useState<NpcFilters>({})
  const { data: npcs } = useNpcs(campaignId, filters)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const { data: entities } = useEntities(campaignId)
  const [selected, setSelected] = useState<string | null>(null)
  const create = useCreateNpc(campaignId ?? '')
  const [name, setName] = useState('')

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const detail = npcs?.find((n) => n.entity_id === selected) ?? null
  const setFilter = (patch: NpcFilters) => setFilters((f) => ({ ...f, ...patch }))
  const active = Object.values(filters).some((v) => v !== undefined && v !== '')

  return (
    <>
      <h2>NPCs</h2>

      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault()
          if (!name.trim()) return
          create.mutate({ name: name.trim() }, { onSuccess: () => setName('') })
        }}
      >
        <div className="row" style={{ gap: 10 }}>
          <input
            placeholder="New NPC…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ flex: 1 }}
          />
          <button type="submit" disabled={!name.trim() || create.isPending}>Add NPC</button>
        </div>
      </form>

      <div className="card npc-queries">
        <h4 style={{ marginTop: 0 }}>Queries</h4>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <label className="field-inline">
            <span className="muted">Status</span>
            <select
              value={filters.status ?? ''}
              onChange={(e) => setFilter({ status: e.target.value || undefined })}
            >
              <option value="">any</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="field-inline">
            <span className="muted">At location</span>
            <select
              value={filters.location_id ?? ''}
              onChange={(e) => setFilter({ location_id: e.target.value || undefined })}
            >
              <option value="">anywhere</option>
              {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          <label className="field-inline">
            <span className="muted">Knows about</span>
            <select
              value={filters.knows ?? ''}
              onChange={(e) => setFilter({ knows: e.target.value || undefined })}
            >
              <option value="">anything</option>
              {entities?.filter((en) => en.entity_type !== 'npc').map((en) => (
                <option key={en.id} value={en.id}>{en.name}</option>
              ))}
            </select>
          </label>
          <label className="field-inline">
            <span className="muted">Met the party</span>
            <input
              type="checkbox"
              checked={filters.met_party === true}
              onChange={(e) => setFilter({ met_party: e.target.checked ? true : undefined })}
            />
          </label>
          {active && (
            <button className="ghost" onClick={() => setFilters({})}>Clear</button>
          )}
        </div>
      </div>

      <ul className="entities">
        {npcs?.length === 0 && <p className="muted">No NPCs match.</p>}
        {npcs?.map((npc) => (
          <li key={npc.entity_id}>
            <button className="linkish" onClick={() => setSelected(npc.entity_id)}>
              {npc.name}
            </button>
            <span className="row" style={{ gap: 6 }}>
              {npc.current_location_name && (
                <span className="badge">📍 {npc.current_location_name}</span>
              )}
              {npc.has_met_party && <span className="badge" title="has met the party">🤝</span>}
              <span className={`badge npc-${npc.status}`}>{npc.status}</span>
              <button
                className="ghost"
                style={{ padding: '4px 8px', fontSize: 12 }}
                onClick={() => setSelected(npc.entity_id)}
              >
                Edit
              </button>
            </span>
          </li>
        ))}
      </ul>

      {detail && (
        <NpcDetail
          campaignId={campaign.id}
          npc={detail}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}

function NpcDetail({
  campaignId,
  npc,
  onClose,
}: {
  campaignId: string
  npc: Npc
  onClose: () => void
}) {
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const { data: history } = useNpcHistory(campaignId, npc.entity_id)
  const { data: schedules } = useNpcSchedules(campaignId, npc.entity_id)
  const { data: sessions } = useSessions(campaignId)
  const relocate = useRelocateNpc(campaignId)
  const setStatus = useSetNpcStatus(campaignId)
  const interact = useRecordInteraction(campaignId)
  const [answer, setAnswer] = useState<string | null>(null)

  // "Where was X during session N" — the server resolves the session's clock span.
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
    <div className="card" style={{ marginTop: 12 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>
          <Link to="/entities/$entityId" params={{ entityId: npc.entity_id }}>{npc.name}</Link>
        </h3>
        <button className="ghost tag-x" onClick={onClose}>×</button>
      </div>

      <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
        <label className="field-inline">
          <span className="muted">Move to</span>
          <select
            value={npc.current_location_id ?? ''}
            onChange={(e) =>
              relocate.mutate({
                npcId: npc.entity_id,
                locationId: e.target.value || null,
                reason: 'GM moved them',
              })
            }
          >
            <option value="">— nowhere —</option>
            {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        <label className="field-inline">
          <span className="muted">Status</span>
          <select
            value={npc.status}
            onChange={(e) => setStatus.mutate({ npcId: npc.entity_id, status: e.target.value })}
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <button onClick={() => interact.mutate({ npcId: npc.entity_id })}>
          {npc.has_met_party ? 'Record interaction' : 'The party met them'}
        </button>
      </div>

      <h4>Where were they…</h4>
      <div className="row" style={{ gap: 8 }}>
        <select defaultValue="" onChange={(e) => askSession(e.target.value)}>
          <option value="">— during which session? —</option>
          {sessions?.map((s) => (
            <option key={s.id} value={s.id}>Session {s.session_number}</option>
          ))}
        </select>
        {answer && <span className="badge">{answer}</span>}
      </div>

      <h4>Location history</h4>
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

      <h4>Itinerary</h4>
      <ul className="entities">
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
  )
}

function ScheduleDelete({ campaignId, scheduleId }: { campaignId: string; scheduleId: string }) {
  const del = useDeleteNpcSchedule(campaignId)
  return (
    <button className="ghost tag-x" onClick={() => del.mutate(scheduleId)}>×</button>
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
            {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
      ))}
      <button type="submit" disabled={!ready || create.isPending} style={{ marginTop: 6 }}>
        Save itinerary
      </button>
    </form>
  )
}
