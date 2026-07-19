import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useCreateNpc,
  useEntities,
  useNpcs,
} from '../../api/hooks'
import type { NpcFilters } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { SearchableSelect } from '../../components/SearchableSelect'

const STATUSES = ['alive', 'dead', 'missing', 'unknown', 'retired'] as const

export function NpcsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const [filters, setFilters] = useState<NpcFilters>({})
  const { data: npcs } = useNpcs(campaignId, filters)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const { data: entities } = useEntities(campaignId)
  const create = useCreateNpc(campaignId ?? '')
  const [name, setName] = useState('')

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

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
            <SearchableSelect
              value={filters.location_id ?? ''}
              onChange={(v) => setFilter({ location_id: v || undefined })}
              options={locations?.map((l) => ({ id: l.id, name: l.name })) ?? []}
              placeholder="anywhere"
            />
          </label>
          <label className="field-inline">
            <span className="muted">Knows about</span>
            <SearchableSelect
              value={filters.knows ?? ''}
              onChange={(v) => setFilter({ knows: v || undefined })}
              options={entities?.filter((en) => en.entity_type !== 'npc').map((en) => ({ id: en.id, name: en.name })) ?? []}
              placeholder="anything"
            />
          </label>
          <label className="field-inline">
            <span className="muted">Met the party</span>
            <input
              type="checkbox"
              checked={filters.met_party === true}
              onChange={(e) => setFilter({ met_party: e.target.checked ? true : undefined })}
            />
          </label>
          <label className="field-inline">
            <span className="muted">Show deleted</span>
            <input
              type="checkbox"
              checked={filters.include_deleted === true}
              // undefined rather than false when off, so it doesn't count as an active filter.
              onChange={(e) => setFilter({ include_deleted: e.target.checked || undefined })}
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
          <li key={npc.entity_id} className={npc.deleted ? 'deleted' : ''}>
            <Link
              className="linkish"
              to="/entities/$entityId"
              params={{ entityId: npc.entity_id }}
            >
              {npc.name}
            </Link>
            <span className="row" style={{ gap: 6 }}>
              {npc.deleted && <span className="tag danger">deleted</span>}
              {npc.current_location_name && (
                <span className="badge">📍 {npc.current_location_name}</span>
              )}
              {npc.has_met_party && <span className="badge" title="has met the party">🤝</span>}
              <span className={`badge npc-${npc.status}`}>{npc.status}</span>
              <Link
                className="ghost"
                style={{ padding: '4px 8px', fontSize: 12, textDecoration: 'none', display: 'inline-block' }}
                to="/entities/$entityId"
                params={{ entityId: npc.entity_id }}
              >
                Edit
              </Link>
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
