import { useEffect, useState } from 'react'
import { Link, useSearch } from '@tanstack/react-router'
import { useCreateEntity, useEntities, usePurgeDeletedEntities, useTags } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { ListToolbar } from '../../components/ListToolbar'
import { useDebounced } from '../../lib/useDebounced'

// Everything the wiki can hold — the create form offers the common authoring types; the
// filter offers all of them so the browse hub can reach maps, encounters, etc.
const CREATE_TYPES = ['note', 'npc', 'location', 'faction', 'quest', 'item'] as const
const ALL_TYPES = [
  'note', 'npc', 'location', 'faction', 'quest', 'monster', 'item', 'map',
  'encounter', 'skill_challenge', 'pc', 'session', 'story_node',
] as const

const SORTS = [
  { value: 'created', label: 'Newest' },
  { value: '-created', label: 'Oldest' },
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: '-updated', label: 'Recently updated' },
]

// Entity hub: create, full-text-ish search, filter by type/tag/deleted, sort, and navigate.
export function EntitiesPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null

  // Browse hubs deep-link via ?type= (e.g. the nav "NPCs" shortcut).
  const search = useSearch({ strict: false }) as { type?: string }
  const [typeFilter, setTypeFilter] = useState<string>(search.type ?? '')
  useEffect(() => setTypeFilter(search.type ?? ''), [search.type])

  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounced(query, 200)
  const [tagFilter, setTagFilter] = useState('')
  const [sort, setSort] = useState('created')
  const [includeDeleted, setIncludeDeleted] = useState(false)

  const { data: tags } = useTags(campaignId)
  const { data: entities } = useEntities(campaignId, {
    ...(typeFilter ? { entity_type: typeFilter } : {}),
    ...(tagFilter ? { tag_id: tagFilter } : {}),
    ...(debouncedQuery.trim() ? { q: debouncedQuery.trim() } : {}),
    include_deleted: includeDeleted,
    sort,
  })
  // Unfiltered count for the "N of M" readout — cheap and gives the search real feedback.
  const { data: allEntities } = useEntities(campaignId, { include_deleted: includeDeleted })

  // Soft-deleted entities linger forever until purged, so the count drives the purge button.
  const { data: withDeleted } = useEntities(campaignId, { include_deleted: true })
  const deletedCount = (withDeleted ?? []).filter((e) => e.deleted).length
  const purge = usePurgeDeletedEntities(campaignId ?? '')

  const doPurge = () => {
    if (
      window.confirm(
        `Permanently delete ${deletedCount} soft-deleted ` +
          `${deletedCount === 1 ? 'entity' : 'entities'}? ` +
          'They cannot be restored afterwards. This cannot be undone.',
      )
    ) {
      purge.mutate()
    }
  }

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
          {CREATE_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
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

      <ListToolbar
        query={query}
        onQuery={setQuery}
        placeholder="Search name & summary…"
        sort={sort}
        onSort={setSort}
        sortOptions={SORTS}
        count={entities?.length}
        total={allEntities?.length}
      >
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {ALL_TYPES.map((t) => (
            <option key={t} value={t}>{t.replace('_', ' ')}</option>
          ))}
        </select>
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="">All tags</option>
          {(tags ?? []).map((t) => (
            <option key={t.id} value={t.id}>#{t.name}</option>
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
        {deletedCount > 0 && (
          <button
            type="button"
            className="danger-btn"
            onClick={doPurge}
            disabled={purge.isPending}
            title="Permanently delete every soft-deleted entity in this campaign"
          >
            {purge.isPending ? 'Purging…' : `Purge ${deletedCount} deleted`}
          </button>
        )}
      </ListToolbar>

      <ul className="entities">
        {entities?.map((entity) => (
          <li key={entity.id} className={entity.deleted ? 'deleted' : ''}>
            <Link to="/entities/$entityId" params={{ entityId: entity.id }}>
              {entity.name}
            </Link>
            <span className="row" style={{ gap: 6 }}>
              {(entity.tags ?? []).map((t) => (
                <span key={t.id} className="tag">#{t.name}</span>
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
        {entities?.length === 0 && (
          <p className="muted">
            {query.trim() || typeFilter || tagFilter
              ? 'No entities match these filters.'
              : 'No entities — create one above.'}
          </p>
        )}
      </ul>
    </>
  )
}
