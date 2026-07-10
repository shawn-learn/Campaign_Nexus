import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { searchEntitiesFts } from '../api/hooks'
import { useUiStore } from '../stores/ui'
import { useRecentsStore } from '../stores/recents'
import { useActiveCampaign } from './useActiveCampaign'
import type { Entity } from '../api/client'

interface EntityRow {
  kind: 'entity'
  id: string
  name: string
  entity_type: string
}
interface CommandRow {
  kind: 'command'
  id: string
  label: string
  run: () => void
}
type Row = EntityRow | CommandRow

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
  const [index, setIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus + reset each time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery('')
      setHits([])
      setIndex(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  // Debounced search.
  useEffect(() => {
    if (!campaignId || !query.trim()) {
      setHits([])
      return
    }
    const handle = setTimeout(() => {
      void searchEntitiesFts(campaignId, query.trim()).then(setHits)
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
    const commandRows = query.trim()
      ? commands.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase()))
      : commands
    return [...entityRows, ...commandRows]
  }, [query, hits, recents, commands])

  useEffect(() => setIndex(0), [rows.length])

  if (!open) return null

  const choose = (row: Row) => {
    if (row.kind === 'entity') openPeek(row.id)
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
