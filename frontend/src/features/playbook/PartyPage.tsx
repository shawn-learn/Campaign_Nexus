import { useState } from 'react'
import {
  useAddPartyMember,
  useParty,
  usePatchParty,
  useRest,
  useStatBlocks,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useCalendar } from '../../lib/useCalendar'
import { TravelPlanner } from './TravelPlanner'

// Party tracker + plugin-driven rests (FR-7, docs/07 §9.4). A rest advances the clock and
// restores party members per the active rule system.
export function PartyPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const cal = useCalendar(campaignId)
  const { data: party } = useParty(campaignId)
  const { data: pcs } = useStatBlocks(campaignId, 'pc')
  const addMember = useAddPartyMember(campaignId ?? '')
  const patch = usePatchParty(campaignId ?? '')
  const rest = useRest(campaignId ?? '')

  const [pick, setPick] = useState('')
  const [restMsg, setRestMsg] = useState<string | null>(null)

  const memberIds = new Set(party?.members.map((m) => m.stat_block_id))
  const available = (pcs ?? []).filter((p) => !memberIds.has(p.id))

  // The rest buttons are whatever the campaign's rule system declares — 5e's short/long,
  // Nimble's field/safe — so this page never names a game system's mechanics.
  const restTypes = party?.rest_types ?? []

  const doRest = (type: string) =>
    rest.mutate(type, {
      onSuccess: (r) => {
        const to = cal ? cal.format(r.to_time).label + ' ' + cal.format(r.to_time).time : `${r.to_time}m`
        setRestMsg(`${type} rest complete — now ${to}`)
      },
    })

  return (
    <>
      <h2>
        Party
        {party?.current_location_name && (
          <span className="badge" style={{ marginLeft: 8 }}>📍 {party.current_location_name}</span>
        )}
      </h2>

      <div className="card row" style={{ justifyContent: 'space-between' }}>
        <label className="row muted" style={{ gap: 6 }}>
          Gold
          <input
            type="number"
            style={{ width: 100 }}
            value={party?.gold ?? 0}
            onChange={(e) => patch.mutate({ gold: Number(e.target.value) })}
          />
        </label>
        <div className="row" style={{ gap: 8 }}>
          {restTypes.map((type) => (
            <button key={type} onClick={() => doRest(type)} disabled={rest.isPending}>
              {type} rest
            </button>
          ))}
          {restTypes.length === 0 && <span className="muted">This system has no rests.</span>}
        </div>
      </div>

      {restMsg && <p className="muted">{restMsg}</p>}

      <ul className="entities">
        {party?.members.map((m) => (
          <li key={m.stat_block_id}>
            <span>{m.name}</span>
            <span className="badge">HP {m.hp} / {m.max_hp}</span>
          </li>
        ))}
        {party?.members.length === 0 && <p className="muted">No party members yet.</p>}
      </ul>

      <div className="card row">
        <select value={pick} onChange={(e) => setPick(e.target.value)} style={{ flex: 1 }}>
          <option value="">Add a PC…</option>
          {available.map((p) => (
            <option key={p.id} value={p.id}>{p.label || '(untitled)'}</option>
          ))}
        </select>
        <button
          disabled={!pick || addMember.isPending}
          onClick={() => { if (pick) { addMember.mutate(pick); setPick('') } }}
        >
          Add
        </button>
      </div>

      {campaign && <TravelPlanner campaignId={campaign.id} systemId={campaign.rule_system_id} />}
    </>
  )
}
