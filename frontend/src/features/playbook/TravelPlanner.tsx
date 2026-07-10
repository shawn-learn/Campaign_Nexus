import { useState } from 'react'
import {
  previewTravel,
  useCommitTravel,
  useEntities,
  useTravelTable,
} from '../../api/hooks'
import type { TravelLegInput } from '../../api/hooks'
import type { TravelPlan } from '../../api/client'

// Travel planner (FR-5.3, docs/07 §9.5): the GM enters legs, the rules plugin prices them,
// and the preview shows what the world does en route *before* anything is committed.
interface LegDraft {
  distance: string
  terrain: string
  pace: string
  conveyance: string
  to_location_id: string
}

function hoursMinutes(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return days ? `${days}d ${hours}h` : `${hours}h`
}

export function TravelPlanner({
  campaignId,
  systemId,
}: {
  campaignId: string
  systemId: string
}) {
  const { data: table } = useTravelTable(systemId)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const commit = useCommitTravel(campaignId)

  const [legs, setLegs] = useState<LegDraft[]>([
    { distance: '24', terrain: 'road', pace: 'normal', conveyance: 'foot', to_location_id: '' },
  ])
  const [forcedMarch, setForcedMarch] = useState(false)
  const [plan, setPlan] = useState<TravelPlan | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [arrived, setArrived] = useState<string | null>(null)

  if (table && !table.supported) {
    return (
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Travel</h3>
        <p className="muted">{systemId} ships no travel rules.</p>
      </div>
    )
  }

  const paces = Object.keys((table?.paces ?? {}) as Record<string, unknown>)
  const conveyances = Object.keys(
    ((table?.paces as Record<string, Record<string, number>>)?.[legs[0]?.pace ?? 'normal'] ?? {}),
  )
  const terrains = Object.keys((table?.terrain ?? {}) as Record<string, unknown>)

  const toInput = (): TravelLegInput[] =>
    legs.map((l) => ({
      distance: Number(l.distance),
      terrain: l.terrain,
      pace: l.pace,
      conveyance: l.conveyance,
      to_location_id: l.to_location_id || null,
    }))

  const doPreview = () => {
    setErr(null)
    setArrived(null)
    previewTravel(campaignId, toInput(), forcedMarch)
      .then(setPlan)
      .catch((e: Error) => { setPlan(null); setErr(e.message) })
  }

  const doCommit = () => {
    commit.mutate(
      { legs: toInput(), forced_march: forcedMarch },
      {
        onSuccess: (r) => {
          setPlan(null)
          setArrived(
            `Arrived${r.destination_name ? ` at ${r.destination_name}` : ''} after ` +
            `${hoursMinutes(r.to_time - r.from_time)}` +
            `${r.rest_stops ? ` and ${r.rest_stops} night(s) on the road` : ''}.`,
          )
        },
        onError: (e) => setErr((e as Error).message),
      },
    )
  }

  const patch = (i: number, p: Partial<LegDraft>) =>
    setLegs((ls) => ls.map((l, j) => (j === i ? { ...l, ...p } : l)))

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Travel</h3>

      {legs.map((leg, i) => (
        <div key={i} className="row travel-leg" style={{ gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          <input
            style={{ width: 70 }}
            value={leg.distance}
            aria-label="distance"
            onChange={(e) => patch(i, { distance: e.target.value })}
          />
          <span className="muted">{table?.distance_unit as string}</span>
          <select value={leg.terrain} onChange={(e) => patch(i, { terrain: e.target.value })}>
            {terrains.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={leg.pace} onChange={(e) => patch(i, { pace: e.target.value })}>
            {paces.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={leg.conveyance} onChange={(e) => patch(i, { conveyance: e.target.value })}>
            {conveyances.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={leg.to_location_id}
            onChange={(e) => patch(i, { to_location_id: e.target.value })}
          >
            <option value="">— to where? —</option>
            {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          {legs.length > 1 && (
            <button className="ghost tag-x" onClick={() => setLegs((ls) => ls.filter((_, j) => j !== i))}>
              ×
            </button>
          )}
        </div>
      ))}

      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <button
          className="ghost"
          onClick={() =>
            setLegs((ls) => [...ls, { distance: '10', terrain: 'road', pace: 'normal', conveyance: 'foot', to_location_id: '' }])
          }
        >
          + leg
        </button>
        <label className="row muted" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={forcedMarch}
            onChange={(e) => setForcedMarch(e.target.checked)}
          />
          Forced march (no overnight rests)
        </label>
        <button onClick={doPreview}>Preview</button>
        {plan && <button onClick={doCommit} disabled={commit.isPending}>Depart</button>}
      </div>

      {err && <p className="tag danger" style={{ marginTop: 8 }}>{err}</p>}
      {arrived && <p className="muted" style={{ marginTop: 8 }}>{arrived}</p>}

      {plan && (
        <div className="travel-plan" style={{ marginTop: 10 }}>
          <p>
            <strong>{hoursMinutes(plan.total_seconds)}</strong> on the road
            {plan.rest_stops > 0 && <> · {plan.rest_stops} long rest(s)</>}
            {' '}· arrive <strong>{plan.arrive_at_label}</strong>
            {plan.destination_name && <> at <strong>{plan.destination_name}</strong></>}
          </p>
          {plan.would_fire.length > 0 && (
            <>
              <h4>The world does not wait</h4>
              <ul className="fired">
                {plan.would_fire.map((f, i) => (
                  <li key={i}>
                    <span className="mono muted">{f.at_label}</span> {f.narrative}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
