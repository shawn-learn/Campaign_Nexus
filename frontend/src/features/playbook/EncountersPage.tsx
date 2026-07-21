import { useMemo, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useEncounters } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { ListToolbar } from '../../components/ListToolbar'
import type { Encounter } from '../../api/client'

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

// The encounter index (FR-12.1). Building one is its own page — this is the list, with the
// rules plugin's difficulty estimate against the current party on each row.
export function EncountersPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: encounters } = useEncounters(campaignId)
  const navigate = useNavigate()

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

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Encounters</h2>
        <button onClick={() => void navigate({ to: '/encounters/new' })}>New encounter</button>
      </div>

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
                to="/encounters/$entityId/edit"
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
