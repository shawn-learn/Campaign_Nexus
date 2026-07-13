import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { searchEntitiesFts, searchMonsters } from '../api/hooks'
import { useUiStore } from '../stores/ui'
import { useRecentsStore } from '../stores/recents'
import { useActiveCampaign } from './useActiveCampaign'
import type { Entity, Monster } from '../api/client'

interface EntityRow {
  kind: 'entity'
  id: string
  name: string
  entity_type: string
}
interface MonsterRow {
  kind: 'monster'
  id: string
  name: string
}
interface CommandRow {
  kind: 'command'
  id: string
  label: string
  run: () => void
}
type Row = EntityRow | MonsterRow | CommandRow

// ⌘K command palette (docs/09-ui-architecture.md, §11.1): global search + commands +
// recents. The most-used control in the app — search must feel instant (NFR-1.2).
export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen)
  const setOpen = useUiStore((s) => s.setPaletteOpen)
  const openPeek = useUiStore((s) => s.openPeek)
  const navigate = useNavigate()
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const recents = useRecentsStore((s) => (campaignId ? s.byCampaign[campaignId] : undefined))

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Entity[]>([])
  const [monsterHits, setMonsterHits] = useState<Monster[]>([])
  const [index, setIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus + reset each time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery('')
      setHits([])
      setMonsterHits([])
      setIndex(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  // Debounced search across entities (ranked FTS) and monsters (separate table).
  useEffect(() => {
    if (!campaignId || !query.trim()) {
      setHits([])
      setMonsterHits([])
      return
    }
    const q = query.trim()
    const handle = setTimeout(() => {
      void searchEntitiesFts(campaignId, q).then(setHits)
      void searchMonsters(campaignId, q).then(setMonsterHits)
    }, 120)
    return () => clearTimeout(handle)
  }, [query, campaignId])

  const commands: CommandRow[] = useMemo(
    () => [
      { kind: 'command', id: 'go-dashboard', label: 'Go to Dashboard', run: () => navigate({ to: '/' }) },
      { kind: 'command', id: 'go-entities', label: 'Go to Entities', run: () => navigate({ to: '/entities' }) },
      { kind: 'command', id: 'browse-npc', label: 'Browse NPCs', run: () => navigate({ to: '/entities', search: { type: 'npc' } }) },
      { kind: 'command', id: 'browse-location', label: 'Browse Locations', run: () => navigate({ to: '/entities', search: { type: 'location' } }) },
    ],
    [navigate],
  )

  const rows: Row[] = useMemo(() => {
    const entityRows: EntityRow[] = query.trim()
      ? hits.map((h) => ({ kind: 'entity', id: h.id, name: h.name, entity_type: h.entity_type }))
      : (recents ?? []).map((r) => ({ kind: 'entity', id: r.id, name: r.name, entity_type: r.entity_type }))
    const monsterRows: MonsterRow[] = query.trim()
      ? monsterHits.map((m) => ({ kind: 'monster', id: m.id, name: m.name }))
      : []
    const commandRows = query.trim()
      ? commands.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase()))
      : commands
    return [...entityRows, ...monsterRows, ...commandRows]
  }, [query, hits, monsterHits, recents, commands])

  useEffect(() => setIndex(0), [rows.length])

  if (!open) return null

  const choose = (row: Row) => {
    if (row.kind === 'entity') openPeek(row.id)
    else if (row.kind === 'monster') navigate({ to: '/bestiary', search: { q: row.name } })
    else row.run()
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setIndex((i) => (rows.length ? (i + 1) % rows.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setIndex((i) => (rows.length ? (i - 1 + rows.length) % rows.length : 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (rows[index]) choose(rows[index])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="palette-overlay" onMouseDown={() => setOpen(false)}>
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Search entities or run a command…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {!query.trim() && <div className="palette-section">Recent</div>}
        <ul className="palette-list">
          {rows.map((row, i) => (
            <li key={`${row.kind}:${row.id}`}>
              <button
                className={'palette-item' + (i === index ? ' active' : '')}
                onMouseEnter={() => setIndex(i)}
                onClick={() => choose(row)}
              >
                {row.kind === 'entity' ? (
                  <>
                    <span>{row.name}</span>
                    <span className="mention-type">{row.entity_type}</span>
                  </>
                ) : row.kind === 'monster' ? (
                  <>
                    <span>{row.name}</span>
                    <span className="mention-type">monster</span>
                  </>
                ) : (
                  <>
                    <span>{row.label}</span>
                    <span className="mention-type">command</span>
                  </>
                )}
              </button>
            </li>
          ))}
          {rows.length === 0 && (
            <li className="palette-empty">
              {query.trim() ? 'No matches.' : 'Type to search…'}
            </li>
          )}
        </ul>
        <div className="palette-hint">↑↓ to move · ↵ to open · esc to close</div>
      </div>
    </div>
  )
}
