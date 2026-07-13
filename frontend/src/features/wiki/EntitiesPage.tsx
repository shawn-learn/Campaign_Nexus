import { useEffect, useState } from 'react'
import { Link, useSearch } from '@tanstack/react-router'
import { useCreateEntity, useEntities } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'

const ENTITY_TYPES = ['note', 'npc', 'location', 'faction', 'quest'] as const

// Entity hub: create, filter by type, toggle deleted, and navigate to detail pages.
export function EntitiesPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null

  // Browse hubs deep-link via ?type= (e.g. the nav "NPCs" shortcut).
  const search = useSearch({ strict: false }) as { type?: string }
  const [typeFilter, setTypeFilter] = useState<string>(search.type ?? '')
  useEffect(() => setTypeFilter(search.type ?? ''), [search.type])
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const { data: entities } = useEntities(campaignId, {
    ...(typeFilter ? { entity_type: typeFilter } : {}),
    include_deleted: includeDeleted,
  })

  const createEntity = useCreateEntity(campaignId ?? '')
  const [name, setName] = useState('')
  const [newType, setNewType] = useState<string>('note')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!campaignId || !name.trim()) return
    createEntity.mutate({ entity_type: newType, name: name.trim() })
    setName('')
  }

  return (
    <>
      <h2>Entities</h2>

      <form className="card row" onSubmit={submit}>
        <select value={newType} onChange={(e) => setNewType(e.target.value)}>
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          placeholder="Name (e.g. Serah Voss)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ flex: 1 }}
        />
        <button type="submit" disabled={!campaignId || createEntity.isPending}>
          {createEntity.isPending ? 'Creating…' : 'Create'}
        </button>
      </form>

      <div className="row filters">
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <label className="row muted" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={includeDeleted}
            onChange={(e) => setIncludeDeleted(e.target.checked)}
          />
          Show deleted
        </label>
      </div>

      <ul className="entities">
        {entities?.map((entity) => (
          <li key={entity.id} className={entity.deleted ? 'deleted' : ''}>
            <Link to="/entities/$entityId" params={{ entityId: entity.id }}>
              {entity.name}
            </Link>
            <span className="row" style={{ gap: 6 }}>
              {(entity.tags ?? []).map((t) => (
                <span key={t.id} className="tag">
                  #{t.name}
                </span>
              ))}
              {entity.deleted && <span className="tag danger">deleted</span>}
              <span className="badge">{entity.entity_type}</span>
              <Link
                to="/entities/$entityId"
                params={{ entityId: entity.id }}
                className="ghost"
                style={{ padding: '4px 8px', fontSize: 12 }}
              >
                Edit
              </Link>
            </span>
          </li>
        ))}
        {entities?.length === 0 && <p className="muted">No entities — create one above.</p>}
      </ul>
    </>
  )
}
