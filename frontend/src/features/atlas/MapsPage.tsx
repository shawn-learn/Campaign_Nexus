import { useMemo, useRef, useState } from 'react'
import {
  useAddMarker,
  useAddRegion,
  useDeleteMap,
  useDeleteMarker,
  useDeleteRegion,
  useEntities,
  useMap,
  useMaps,
  useUpdateMarker,
  useUploadMap,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useUiStore } from '../../stores/ui'
import { LeafletMap } from './LeafletMap'
import type { MapTool } from './LeafletMap'
import type { MapMarker, MapRegion } from '../../api/client'

const MAP_KINDS = ['world', 'region', 'city', 'dungeon', 'building'] as const

// The Atlas (FR-3): upload an image, drop entity-linked markers on a CRS.Simple canvas,
// and drill world → city → dungeon via child-map markers with a breadcrumb stack back.
export function MapsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: maps } = useMaps(campaignId)

  // Drill-down stack: last entry is the map currently shown.
  const [stack, setStack] = useState<{ id: string; name: string }[]>([])
  const current = stack[stack.length - 1] ?? null
  const { data: detail } = useMap(campaignId, current?.id ?? null)
  const [edit, setEdit] = useState(false)

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const open = (id: string, name: string) => setStack([{ id, name }])
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
  maps: { entity_id: string; name: string; map_kind: string; marker_count: number }[]
  onOpen: (id: string, name: string) => void
}) {
  const upload = useUploadMap(campaignId)
  const del = useDeleteMap(campaignId)
  const fileRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<string>('region')
  const [err, setErr] = useState<string | null>(null)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file || !name.trim()) return
    setErr(null)
    upload.mutate(
      { file, name: name.trim(), mapKind: kind },
      {
        onSuccess: (m) => {
          setName('')
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
        {err && <p className="tag danger" style={{ marginTop: 8 }}>{err}</p>}
      </form>

      <ul className="entities">
        {maps.length === 0 && <p className="muted">No maps yet. Upload one to begin.</p>}
        {maps.map((m) => (
          <li key={m.entity_id}>
            <button className="linkish" onClick={() => onOpen(m.entity_id, m.name)}>{m.name}</button>
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

function MapCanvas({
  campaignId,
  detail,
  edit,
  onDrill,
}: {
  campaignId: string
  detail: import('../../api/client').MapDetail
  edit: boolean
  onDrill: (id: string, name: string) => void
}) {
  const openPeek = useUiStore((s) => s.openPeek)
  const addMarker = useAddMarker(campaignId, detail.entity_id)
  const updateMarker = useUpdateMarker(campaignId, detail.entity_id)
  const deleteMarker = useDeleteMarker(campaignId, detail.entity_id)
  const addRegion = useAddRegion(campaignId, detail.entity_id)
  const deleteRegion = useDeleteRegion(campaignId, detail.entity_id)

  const [tool, setTool] = useState<MapTool>('pin')
  const [pending, setPending] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<[number, number][]>([])
  const [hidden, setHidden] = useState<string[]>([])

  const layers = detail.layers ?? []
  const imageUrl = useMemo(
    () => `/api/v1/campaigns/${campaignId}/maps/${detail.entity_id}/image`,
    [campaignId, detail.entity_id],
  )

  // Play mode: a pin peeks its entity or drills into its child map. Edit mode deletes.
  const onMarkerClick = (m: MapMarker) => {
    if (edit) {
      if (confirm('Delete this marker?')) deleteMarker.mutate(m.id)
      return
    }
    if (m.child_map_id && m.child_map_name) onDrill(m.child_map_id, m.child_map_name)
    else if (m.target_entity_id) openPeek(m.target_entity_id)
  }

  const onRegionClick = (r: MapRegion) => {
    if (edit) {
      if (confirm(`Delete region “${r.name ?? 'unnamed'}”?`)) deleteRegion.mutate(r.id)
      return
    }
    if (r.child_map_id && r.child_map_name) onDrill(r.child_map_id, r.child_map_name)
    else if (r.target_entity_id) openPeek(r.target_entity_id)
  }

  const onMapClick = (x: number, y: number) => {
    if (!edit) return
    if (tool === 'pin') setPending({ x, y })
    else setDraft((d) => [...d, [x, y]])
  }

  const onMarkerMove = (marker: MapMarker, x: number, y: number) => {
    if (!edit) return
    updateMarker.mutate({ markerId: marker.id, patch: { x, y } })
  }

  const toggleLayer = (layer: string) =>
    setHidden((h) => (h.includes(layer) ? h.filter((l) => l !== layer) : [...h, layer]))

  const switchTool = (next: MapTool) => {
    setTool(next)
    setPending(null)
    setDraft([])
  }

  return (
    <>
      {layers.length > 1 && (
        <div className="row layer-chips" style={{ gap: 6, marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>Layers</span>
          {layers.map((l) => (
            <button
              key={l}
              className={'chip' + (hidden.includes(l) ? ' off' : '')}
              onClick={() => toggleLayer(l)}
            >
              {l}
            </button>
          ))}
        </div>
      )}

      <div className="map-layout">
        <LeafletMap
          imageUrl={imageUrl}
          width={detail.width_px}
          height={detail.height_px}
          markers={detail.markers}
          regions={detail.regions ?? []}
          hiddenLayers={hidden}
          editMode={edit}
          tool={tool}
          draft={draft}
          onMapClick={onMapClick}
          onMarkerClick={onMarkerClick}
          onRegionClick={onRegionClick}
          onMarkerMove={onMarkerMove}
        />
        {edit && (
          <div className="map-side card">
            <div className="row" style={{ gap: 6, marginBottom: 10 }}>
              <button className={tool === 'pin' ? '' : 'ghost'} onClick={() => switchTool('pin')}>
                Pin
              </button>
              <button
                className={tool === 'region' ? '' : 'ghost'}
                onClick={() => switchTool('region')}
              >
                Region
              </button>
            </div>

            {tool === 'pin' && (
              <>
                <h4 style={{ marginTop: 0 }}>Add marker</h4>
                {!pending && <p className="muted">Click the map to place a pin.</p>}
                {pending && (
                  <NewMarkerForm
                    campaignId={campaignId}
                    currentMapId={detail.entity_id}
                    at={pending}
                    onCancel={() => setPending(null)}
                    onSubmit={(body) =>
                      addMarker.mutate(
                        { ...body, x: pending.x, y: pending.y },
                        { onSuccess: () => setPending(null) },
                      )
                    }
                  />
                )}
              </>
            )}

            {tool === 'region' && (
              <>
                <h4 style={{ marginTop: 0 }}>Draw region</h4>
                <p className="muted" style={{ fontSize: 12 }}>
                  Click to drop vertices — {draft.length} placed
                  {draft.length < 3 && ` (${3 - draft.length} more needed)`}.
                </p>
                {draft.length >= 3 && (
                  <NewRegionForm
                    campaignId={campaignId}
                    currentMapId={detail.entity_id}
                    onCancel={() => setDraft([])}
                    onSubmit={(body) =>
                      addRegion.mutate(
                        { ...body, polygon: draft },
                        { onSuccess: () => setDraft([]) },
                      )
                    }
                  />
                )}
                {draft.length > 0 && draft.length < 3 && (
                  <button className="ghost" onClick={() => setDraft([])}>Clear</button>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}

function NewRegionForm({
  campaignId,
  currentMapId,
  onCancel,
  onSubmit,
}: {
  campaignId: string
  currentMapId: string
  onCancel: () => void
  onSubmit: (body: {
    name?: string | null
    layer?: string
    target_entity_id?: string | null
    child_map_id?: string | null
  }) => void
}) {
  const { data: entities } = useEntities(campaignId)
  const { data: maps } = useMaps(campaignId)
  const [name, setName] = useState('')
  const [layer, setLayer] = useState('default')
  const [target, setTarget] = useState('')
  const [child, setChild] = useState('')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({
          name: name.trim() || null,
          layer: layer.trim() || 'default',
          target_entity_id: target || null,
          child_map_id: child || null,
        })
      }}
    >
      <label className="field">
        <span className="muted">Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Neverwinter Wood" />
      </label>
      <label className="field">
        <span className="muted">Layer</span>
        <input value={layer} onChange={(e) => setLayer(e.target.value)} />
      </label>
      <label className="field">
        <span className="muted">Links to entity</span>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">— none —</option>
          {entities?.filter((en) => en.entity_type !== 'map').map((en) => (
            <option key={en.id} value={en.id}>{en.name} ({en.entity_type})</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="muted">Drills into map</span>
        <select value={child} onChange={(e) => setChild(e.target.value)}>
          <option value="">— none —</option>
          {maps?.filter((m) => m.entity_id !== currentMapId).map((m) => (
            <option key={m.entity_id} value={m.entity_id}>{m.name}</option>
          ))}
        </select>
      </label>
      <div className="row" style={{ gap: 6, marginTop: 8 }}>
        <button type="submit">Save region</button>
        <button type="button" className="ghost" onClick={onCancel}>Clear</button>
      </div>
    </form>
  )
}

function NewMarkerForm({
  campaignId,
  currentMapId,
  at,
  onCancel,
  onSubmit,
}: {
  campaignId: string
  currentMapId: string
  at: { x: number; y: number }
  onCancel: () => void
  onSubmit: (body: {
    target_entity_id?: string | null
    child_map_id?: string | null
    note?: string | null
    layer?: string
  }) => void
}) {
  const { data: entities } = useEntities(campaignId)
  const { data: maps } = useMaps(campaignId)
  const [target, setTarget] = useState('')
  const [child, setChild] = useState('')
  const [note, setNote] = useState('')
  const [layer, setLayer] = useState('default')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({
          target_entity_id: target || null,
          child_map_id: child || null,
          note: note.trim() || null,
          layer: layer.trim() || 'default',
        })
      }}
    >
      <p className="muted" style={{ fontSize: 12 }}>at ({Math.round(at.x)}, {Math.round(at.y)})</p>
      <label className="field">
        <span className="muted">Links to entity</span>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">— none —</option>
          {entities?.filter((en) => en.entity_type !== 'map').map((en) => (
            <option key={en.id} value={en.id}>{en.name} ({en.entity_type})</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="muted">Drills into map</span>
        <select value={child} onChange={(e) => setChild(e.target.value)}>
          <option value="">— none —</option>
          {maps?.filter((m) => m.entity_id !== currentMapId).map((m) => (
            <option key={m.entity_id} value={m.entity_id}>{m.name}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="muted">Note</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" />
      </label>
      <label className="field">
        <span className="muted">Layer</span>
        <input value={layer} onChange={(e) => setLayer(e.target.value)} />
      </label>
      <div className="row" style={{ gap: 6, marginTop: 8 }}>
        <button type="submit">Place</button>
        <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
