import { useState } from 'react'
import {
  previewTravel,
  useCommitTravel,
  useEntities,
  useTravelTable,
} from '../../api/hooks'
import type { TravelLegInput } from '../../api/hooks'
import type { TravelPlan } from '../../api/client'
import { SearchableSelect } from '../../components/SearchableSelect'

export interface LegDraft {
  distance: string
  terrain: string
  to_location_id: string
  travel_type?: string
}

export function hoursMinutes(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return days ? `${days}d ${hours}h` : `${hours}h`
}

export const RULES_HELP: Record<string, string> = {
  normal: 'Standard travel pace. No mechanical benefits or penalties.',
  'forced march': 'Forced March: Risks exhaustion. Requires Constitution saving throws starting at DC 10, increasing by +1 for each additional hour beyond 8 hours traveled per day.',
  mounted: 'Mounted Travel: Mounts do not increase daily travel distance. Mounted characters bypass heavy armor Strength requirements (no speed penalty) and gain combat mobility advantages.',
  'gallop difficult terrain': 'Gallop + Difficult Terrain: Mount speed is doubled for 1 hour per day, once per long rest. Difficult terrain cuts daily travel distance in half.',
  'slow (sneak)': 'Slow (Sneak) Pace: Allows moving stealthily. Grants Advantage on Wisdom (Perception) and Wisdom (Survival) checks.',
  'mounted difficult terrain': 'Mounted + Difficult Terrain: Mounts do not increase daily travel distance. Difficult terrain cuts daily travel distance in half.',
  'difficult terrain': 'Difficult Terrain: Cuts the total distance traveled per day in half (doubles travel time).',
}

export function TravelPlanner({
  campaignId,
  systemId,
  legs: controlledLegs,
  onLegsChange: controlledSetLegs,
}: {
  campaignId: string
  systemId: string
  legs?: LegDraft[]
  onLegsChange?: React.Dispatch<React.SetStateAction<LegDraft[]>>
}) {
  const { data: table } = useTravelTable(systemId)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const commit = useCommitTravel(campaignId)

  const [internalLegs, setInternalLegs] = useState<LegDraft[]>([
    { distance: '24', terrain: 'road', to_location_id: '', travel_type: 'normal' },
  ])
  const legs = controlledLegs ?? internalLegs
  const setLegs = controlledSetLegs ?? setInternalLegs
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

  const terrains = Object.keys((table?.terrain ?? {}) as Record<string, unknown>)
  const isForcedMarchActive = legs.some((l) => l.travel_type === 'forced march')

  const toInput = (): TravelLegInput[] =>
    legs.map((l) => ({
      distance: Number(l.distance),
      terrain: l.terrain,
      to_location_id: l.to_location_id || null,
      travel_type: l.travel_type || 'normal',
    }))

  const doPreview = () => {
    setErr(null)
    setArrived(null)
    previewTravel(campaignId, toInput(), isForcedMarchActive)
      .then((data) => setPlan(data as unknown as TravelPlan))
      .catch((e: Error) => { setPlan(null); setErr(e.message) })
  }

  const doCommit = () => {
    commit.mutate(
      { legs: toInput(), forced_march: isForcedMarchActive },
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
          <select
            value={leg.travel_type || 'normal'}
            onChange={(e) => patch(i, { travel_type: e.target.value })}
            aria-label="travel type"
          >
            <option value="normal">Normal (Foot)</option>
            <option value="forced march">Forced March (Foot)</option>
            <option value="mounted">Mounted (Horse)</option>
            <option value="gallop difficult terrain">Gallop + Diff Terrain (Horse)</option>
            <option value="slow (sneak)">Slow / Sneak (Foot)</option>
            <option value="mounted difficult terrain">Mounted + Diff Terrain (Horse)</option>
            <option value="difficult terrain">Difficult Terrain (Foot)</option>
          </select>
          <SearchableSelect
            value={leg.to_location_id}
            onChange={(v) => patch(i, { to_location_id: v })}
            options={locations?.map((l) => ({ id: l.id, name: l.name })) ?? []}
            placeholder="— to where? —"
          />
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
            setLegs((ls) => [...ls, { distance: '10', terrain: 'road', to_location_id: '', travel_type: 'normal' }])
          }
        >
          + leg
        </button>
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

          {/* Rules Advisory */}
          <div style={{ marginTop: 12, padding: 8, background: 'var(--bg-light, rgba(255,255,255,0.05))', borderRadius: 4, fontSize: 12 }}>
            <h4 style={{ margin: '0 0 6px 0', fontSize: 13 }}>Travel Rules Advice</h4>
            <ul style={{ paddingLeft: 16, margin: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Array.from(new Set(legs.map((l) => l.travel_type || 'normal'))).map((tt) => (
                <li key={tt} style={{ listStyleType: 'disc' }}>
                  <strong>{tt}</strong>: {RULES_HELP[tt] || RULES_HELP.normal}
                </li>
              ))}
            </ul>
          </div>

          {/* Forced March Saves */}
          {plan.forced_march_saves && plan.forced_march_saves.length > 0 && (
            <div style={{ marginTop: 12, padding: 8, border: '1px solid var(--danger, #e05252)', borderRadius: 4, fontSize: 12 }}>
              <h4 style={{ margin: '0 0 6px 0', color: 'var(--danger, #e05252)', fontSize: 13 }}>
                ⚠️ Forced March Constitution Saves Required
              </h4>
              <p className="muted" style={{ margin: '0 0 8px 0', fontSize: 11 }}>
                A Constitution save at the end of each hour beyond 8 hours of travel; the DC resets each day:
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 6 }}>
                {plan.forced_march_saves.map((s: { hour: number; day?: number; dc: number }) => (
                  <div key={s.hour} className="card" style={{ padding: '4px 8px', textAlign: 'center', margin: 0 }}>
                    <div className="muted" style={{ fontSize: 10 }}>
                      {s.day && s.day > 1 ? `Day ${s.day} · ` : ''}Hour {s.hour}
                    </div>
                    <div style={{ fontWeight: 'bold', fontSize: 14 }}>DC {s.dc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {plan.would_fire.length > 0 && (
            <>
              <h4 style={{ marginTop: 14, marginBottom: 6 }}>The world does not wait</h4>
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
