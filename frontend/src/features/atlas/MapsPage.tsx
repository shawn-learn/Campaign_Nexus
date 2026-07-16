import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  useDeleteMap,
  useMap,
  useMaps,
  useUploadMap,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { ListToolbar } from '../../components/ListToolbar'
import type { MapSummary } from '../../api/client'
import { MapCanvas } from './MapCanvasComponents'

const MAP_KINDS = ['world', 'region', 'city', 'dungeon', 'building'] as const

const MAP_SORTS = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: 'kind', label: 'Kind' },
  { value: '-pins', label: 'Most pins' },
]

export function MapsPage() {
  const navigate = useNavigate()
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: maps } = useMaps(campaignId)

  const [stack, setStack] = useState<{ id: string; name: string }[]>([])
  const current = stack[stack.length - 1] ?? null
  const { data: detail } = useMap(campaignId, current?.id ?? null)
  const [edit, setEdit] = useState(false)

  const { open: openParam } = useSearch({ from: '/maps' })
  useEffect(() => {
    if (!openParam || !maps) return
    const target = maps.find((m) => m.entity_id === openParam)
    if (target) {
      if (target.location_id) {
        navigate({
          to: '/entities/$entityId',
          params: { entityId: target.location_id },
          search: { tab: 'map' },
        })
      } else {
        setStack([{ id: target.entity_id, name: target.name }])
      }
    }
  }, [openParam, maps, navigate])

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const open = (id: string, name: string) => {
    const target = maps?.find((m) => m.entity_id === id)
    if (target?.location_id) {
      navigate({
        to: '/entities/$entityId',
        params: { entityId: target.location_id },
        search: { tab: 'map' },
      })
    } else {
      setStack([{ id, name }])
    }
  }
  const drill = (id: string, name: string) => setStack((s) => [...s, { id, name }])
  const popTo = (i: number) => setStack((s) => s.slice(0, i + 1))

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Atlas</h2>
        {current && (
          <button className={edit ? '' : 'ghost'} onClick={() => setEdit((e) => !e)}>
            {edit ? 'Editing — done' : 'Edit markers'}
          </button>
        )}
      </div>

      {!current && (
        <MapLibrary campaignId={campaign.id} maps={maps ?? []} onOpen={open} />
      )}

      {current && (
        <>
          <div className="breadcrumb row" style={{ marginBottom: 8 }}>
            <button className="linkish" onClick={() => setStack([])}>Atlas</button>
            {stack.map((s, i) => (
              <span key={s.id}>
                <span className="muted"> ▸ </span>
                <button className="linkish" onClick={() => popTo(i)}>{s.name}</button>
              </span>
            ))}
          </div>
          {detail && (
            <MapCanvas
              key={detail.entity_id}
              campaignId={campaign.id}
              detail={detail}
              edit={edit}
              onDrill={drill}
            />
          )}
        </>
      )}
    </>
  )
}

function MapLibrary({
  campaignId,
  maps,
  onOpen,
}: {
  campaignId: string
  maps: MapSummary[]
  onOpen: (id: string, name: string) => void
}) {
  const upload = useUploadMap(campaignId)
  const del = useDeleteMap(campaignId)
  const fileRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<string>('region')
  const [description, setDescription] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [linked, setLinked] = useState('')
  const [sort, setSort] = useState('name')

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rows = maps.filter((m) => {
      if (kindFilter && m.map_kind !== kindFilter) return false
      if (linked === 'yes' && !m.location_id) return false
      if (linked === 'no' && m.location_id) return false
      if (q && !`${m.name} ${m.description ?? ''}`.toLowerCase().includes(q)) return false
      return true
    })
    const dir = sort.startsWith('-') ? -1 : 1
    const key = sort.replace('-', '')
    return [...rows].sort((a, b) => {
      if (key === 'pins') return (a.marker_count - b.marker_count) * dir
      if (key === 'kind') return a.map_kind.localeCompare(b.map_kind) * dir || a.name.localeCompare(b.name)
      return a.name.localeCompare(b.name) * dir
    })
  }, [maps, query, kindFilter, linked, sort])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file || !name.trim()) return
    setErr(null)
    upload.mutate(
      { file, name: name.trim(), mapKind: kind, description: description.trim() || null },
      {
        onSuccess: (m) => {
          setName('')
          setDescription('')
          if (fileRef.current) fileRef.current.value = ''
          onOpen(m.entity_id, m.name)
        },
        onError: (e2) => setErr((e2 as Error).message),
      },
    )
  }

  return (
    <>
      <form className="card" onSubmit={submit}>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" />
          <input placeholder="Map name" value={name} onChange={(e) => setName(e.target.value)} />
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {MAP_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <button type="submit" disabled={upload.isPending}>Upload map</button>
        </div>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional) — e.g. the write-up for the Village of Barovia"
          rows={2}
          style={{ marginTop: 8, width: '100%' }}
        />
        {err && <p className="tag danger" style={{ marginTop: 8 }}>{err}</p>}
      </form>

      {maps.length > 0 && (
        <ListToolbar
          query={query}
          onQuery={setQuery}
          placeholder="Search maps…"
          sort={sort}
          onSort={setSort}
          sortOptions={MAP_SORTS}
          count={shown.length}
          total={maps.length}
        >
          <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
            <option value="">All kinds</option>
            {MAP_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <select value={linked} onChange={(e) => setLinked(e.target.value)}>
            <option value="">Any location</option>
            <option value="yes">Linked to a location</option>
            <option value="no">Not linked</option>
          </select>
        </ListToolbar>
      )}

      <ul className="entities">
        {maps.length === 0 && <p className="muted">No maps yet. Upload one to begin.</p>}
        {maps.length > 0 && shown.length === 0 && (
          <p className="muted">No maps match these filters.</p>
        )}
        {shown.map((m) => (
          <li key={m.entity_id}>
            <div style={{ minWidth: 0 }}>
              <button className="linkish" onClick={() => onOpen(m.entity_id, m.name)}>{m.name}</button>
              {m.description && (
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{m.description}</div>
              )}
            </div>
            <span className="row" style={{ gap: 6 }}>
              <span className="badge">{m.map_kind}</span>
              <span className="badge">{m.marker_count} pins</span>
              <button
                className="ghost"
                style={{ padding: '4px 8px', fontSize: 12 }}
                onClick={() => onOpen(m.entity_id, m.name)}
              >
                Edit map
              </button>
              <button
                className="ghost tag-x"
                title="Delete map"
                onClick={() => { if (confirm(`Delete map “${m.name}”?`)) del.mutate(m.entity_id) }}
              >
                ×
              </button>
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
