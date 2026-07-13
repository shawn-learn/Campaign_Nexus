import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useCreateEncounter,
  useEncounters,
  useMonsters,
} from '../../api/hooks'
import { searchEntities } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { ListToolbar } from '../../components/ListToolbar'
import type { Encounter, Entity } from '../../api/client'

const DIFF_CLASS: Record<string, string> = {
  trivial: 'diff-trivial', easy: 'diff-easy', medium: 'diff-medium',
  hard: 'diff-hard', deadly: 'diff-deadly',
}
// Ascending threat, used both for the filter list and as the sort key.
const DIFF_ORDER = ['trivial', 'easy', 'medium', 'hard', 'deadly']

const ENC_SORTS = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: '-difficulty', label: 'Hardest first' },
  { value: 'difficulty', label: 'Easiest first' },
]

// Encounter builder (FR-12.1): monsters + terrain, difficulty estimated by the rules
// plugin against the current party, linkable to a location.
export function EncountersPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: encounters } = useEncounters(campaignId)
  const { data: monsters } = useMonsters(campaignId)
  const create = useCreateEncounter(campaignId ?? '')

  const [name, setName] = useState('')
  const [terrain, setTerrain] = useState('')
  const [picks, setPicks] = useState<Record<string, number>>({})
  const [location, setLocation] = useState<Entity | null>(null)
  const [locQuery, setLocQuery] = useState('')
  const [locResults, setLocResults] = useState<Entity[]>([])

  // Browse controls (client-side — the encounter list is small).
  const [query, setQuery] = useState('')
  const [diffFilter, setDiffFilter] = useState('')
  const [sort, setSort] = useState('name')

  const diffRank = (e: Encounter) =>
    e.difficulty.difficulty ? DIFF_ORDER.indexOf(e.difficulty.difficulty) : -1
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rows = (encounters ?? []).filter((e) => {
      if (diffFilter && e.difficulty.difficulty !== diffFilter) return false
      if (q && !e.name.toLowerCase().includes(q)) return false
      return true
    })
    const dir = sort.startsWith('-') ? -1 : 1
    const key = sort.replace('-', '')
    return [...rows].sort((a, b) =>
      key === 'difficulty'
        ? (diffRank(a) - diffRank(b)) * dir || a.name.localeCompare(b.name)
        : a.name.localeCompare(b.name) * dir,
    )
  }, [encounters, query, diffFilter, sort])

  const searchLoc = (q: string) => {
    setLocQuery(q)
    if (!campaignId || !q.trim()) return setLocResults([])
    void searchEntities(campaignId, q.trim()).then((hits) =>
      setLocResults(hits.filter((h) => h.entity_type === 'location').slice(0, 5)),
    )
  }

  const bump = (id: string, delta: number) =>
    setPicks((p) => {
      const next = Math.max(0, (p[id] ?? 0) + delta)
      const copy = { ...p }
      if (next === 0) delete copy[id]
      else copy[id] = next
      return copy
    })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    const combatants = Object.entries(picks).map(([monster_id, count]) => ({ monster_id, count }))
    create.mutate(
      { name: name.trim(), terrain: terrain || null, combatants,
        location_id: location?.id ?? null },
      { onSuccess: () => { setName(''); setTerrain(''); setPicks({}); setLocation(null); setLocQuery('') } },
    )
  }

  return (
    <>
      <h2>Encounters</h2>

      <form className="card" onSubmit={submit}>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <input placeholder="Encounter name" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1 }} />
          <input placeholder="Terrain" value={terrain} onChange={(e) => setTerrain(e.target.value)} />
        </div>

        <div className="relation-form" style={{ marginTop: 8 }}>
          {location ? (
            <span className="chosen-target">
              at {location.name}
              <button type="button" className="tag-x" onClick={() => setLocation(null)}>×</button>
            </span>
          ) : (
            <input placeholder="Link to a location…" value={locQuery} onChange={(e) => searchLoc(e.target.value)} />
          )}
          {locResults.length > 0 && !location && (
            <ul className="picker">
              {locResults.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => { setLocation(r); setLocResults([]) }}>
                    <span>{r.name}</span><span className="mention-type">location</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <h4 style={{ margin: '12px 0 6px' }}>Monsters</h4>
        <div className="picker-grid">
          {monsters?.map((m) => (
            <div key={m.id} className={'pick-row' + (picks[m.id] ? ' picked' : '')}>
              <span>{m.name} <span className="muted">CR {m.facets.facet1_num ?? '?'}</span></span>
              <span className="row" style={{ gap: 6 }}>
                <button type="button" onClick={() => bump(m.id, -1)}>−</button>
                <span style={{ minWidth: 16, textAlign: 'center' }}>{picks[m.id] ?? 0}</span>
                <button type="button" onClick={() => bump(m.id, +1)}>+</button>
              </span>
            </div>
          ))}
        </div>

        <button type="submit" disabled={!name.trim() || create.isPending} style={{ marginTop: 10 }}>
          Build encounter
        </button>
      </form>

      {(encounters?.length ?? 0) > 0 && (
        <ListToolbar
          query={query}
          onQuery={setQuery}
          placeholder="Search encounters…"
          sort={sort}
          onSort={setSort}
          sortOptions={ENC_SORTS}
          count={shown.length}
          total={encounters?.length}
        >
          <select value={diffFilter} onChange={(e) => setDiffFilter(e.target.value)}>
            <option value="">All difficulties</option>
            {DIFF_ORDER.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </ListToolbar>
      )}

      <ul className="entities">
        {shown.map((enc) => (
          <li key={enc.id}>
            <Link to="/entities/$entityId" params={{ entityId: enc.id }}>{enc.name}</Link>
            <span className="row" style={{ gap: 8 }}>
              {enc.difficulty.supported && enc.difficulty.difficulty && (
                <span className={'badge ' + (DIFF_CLASS[enc.difficulty.difficulty] ?? '')}>
                  {enc.difficulty.difficulty} · {enc.difficulty.adjusted_xp} XP
                </span>
              )}
              <span className="muted">{enc.combatants.reduce((n, c) => n + c.count, 0)} foes</span>
              <Link
                to="/entities/$entityId"
                params={{ entityId: enc.id }}
                className="ghost"
                style={{ padding: '4px 8px', fontSize: 12 }}
              >
                Edit
              </Link>
            </span>
          </li>
        ))}
        {encounters?.length === 0 && <p className="muted">No encounters yet.</p>}
        {(encounters?.length ?? 0) > 0 && shown.length === 0 && (
          <p className="muted">No encounters match these filters.</p>
        )}
      </ul>
    </>
  )
}
