import { useEffect, useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useAddMarker,
  useAddRegion,
  useDeleteMarker,
  useDeleteRegion,
  useEntities,
  useMaps,
  useSetMapLocation,
  useUpdateMap,
  useUpdateMarker,
  useParty,
  usePatchParty,
  useConnections,
  useCommitTravel,
  previewTravel,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useUiStore } from '../../stores/ui'
import { LeafletMap } from './LeafletMap'
import type { MapTool } from './LeafletMap'
import { TravelPlanner, RULES_HELP, hoursMinutes } from '../playbook/TravelPlanner'
import type { LegDraft } from '../playbook/TravelPlanner'
import type { MapMarker, MapRegion, MapDetail, TravelPlan } from '../../api/client'

export function MapCanvas({
  campaignId,
  detail,
  edit,
  onDrill,
}: {
  campaignId: string
  detail: MapDetail
  edit: boolean
  onDrill: (id: string, name: string) => void
}) {
  const openPeek = useUiStore((s) => s.openPeek)
  const addMarker = useAddMarker(campaignId, detail.entity_id)
  const updateMarker = useUpdateMarker(campaignId, detail.entity_id)
  const deleteMarker = useDeleteMarker(campaignId, detail.entity_id)
  const addRegion = useAddRegion(campaignId, detail.entity_id)
  const deleteRegion = useDeleteRegion(campaignId, detail.entity_id)
  const updateMap = useUpdateMap(campaignId, detail.entity_id)
  
  const { data: party } = useParty(campaignId)
  const patchParty = usePatchParty(campaignId)
  const commitTravel = useCommitTravel(campaignId)
  const { data: connections } = useConnections(campaignId)
  const { campaign } = useActiveCampaign()

  const handleTravel = (distance: number, travelType: string) => {
    const isForcedMarch = travelType === 'forced march'
    commitTravel.mutate(
      {
        legs: [{ distance, terrain: 'road', travel_type: travelType }],
        forced_march: isForcedMarch,
      },
      {
        onSuccess: () => {
          if (draft.length > 0) {
            const lastPoint = draft[draft.length - 1]
            patchParty.mutate({
              current_map_id: detail.entity_id,
              current_x: lastPoint[0],
              current_y: lastPoint[1],
              coordinates_set: true,
              current_location_id: null,
              location_set: true,
            })
          }
          setDraft([])
        },
        onError: (err) => {
          alert('Travel failed: ' + (err as Error).message)
        },
      }
    )
  }

  const [tool, setTool] = useState<MapTool>(() => {
    const hasScale = detail.scale_pixels_per_unit && detail.scale_pixels_per_unit > 0
    return hasScale ? 'pin' : 'ruler'
  })
  const [pending, setPending] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<[number, number][]>([])
  const [hidden, setHidden] = useState<string[]>([])
  
  const [travelMode, setTravelMode] = useState(false)
  const [travelLegs, setTravelLegs] = useState<LegDraft[]>([])

  const layers = detail.layers ?? []
  const imageUrl = useMemo(
    () => `/api/v1/campaigns/${campaignId}/maps/${detail.entity_id}/image`,
    [campaignId, detail.entity_id],
  )

  const getDistanceBetween = (fromId: string, toId: string): { distance: number; terrain: string } => {
    const conn = connections?.find(
      (c) =>
        (c.from_location_id === fromId && c.to_location_id === toId) ||
        (c.from_location_id === toId && c.to_location_id === fromId)
    )
    if (conn) {
      return { distance: conn.distance, terrain: conn.terrain }
    }

    const m1 = detail.markers.find((m) => m.target_entity_id === fromId)
    const m2 = detail.markers.find((m) => m.target_entity_id === toId)
    if (m1 && m2) {
      const px = Math.sqrt((m1.x - m2.x) ** 2 + (m1.y - m2.y) ** 2)
      const scale = detail.scale_pixels_per_unit
      if (scale && scale > 0) {
        return { distance: Math.round((px / scale) * 10) / 10, terrain: 'road' }
      }
      return { distance: Math.round(px), terrain: 'road' }
    }
    return { distance: 10, terrain: 'road' }
  }

  const onMarkerClick = (m: MapMarker) => {
    if (travelMode && m.target_entity_id) {
      const toId = m.target_entity_id
      const fromId = travelLegs.length > 0 
        ? travelLegs[travelLegs.length - 1].to_location_id 
        : party?.current_location_id

      if (fromId && toId && fromId !== toId) {
        const { distance, terrain } = getDistanceBetween(fromId, toId)
        setTravelLegs((prev) => [
          ...prev,
          { distance: String(distance), terrain, to_location_id: toId, travel_type: 'normal' },
        ])
        setDraft((d) => [...d, [m.x, m.y]])
      }
      return
    }

    if (tool === 'ruler') {
      setDraft((d) => [...d, [m.x, m.y]])
      return
    }

    if (edit) {
      if (confirm('Delete this marker?')) deleteMarker.mutate(m.id)
      return
    }
    if (m.child_map_id && m.child_map_name) onDrill(m.child_map_id, m.child_map_name)
    else if (m.target_entity_id) openPeek(m.target_entity_id)
  }

  const onRegionClick = (r: MapRegion) => {
    if (travelMode && r.target_entity_id) {
      const toId = r.target_entity_id
      const fromId = travelLegs.length > 0 
        ? travelLegs[travelLegs.length - 1].to_location_id 
        : party?.current_location_id

      if (fromId && toId && fromId !== toId && r.polygon.length > 0) {
        const xs = r.polygon.map((p) => p[0])
        const ys = r.polygon.map((p) => p[1])
        const cx = xs.reduce((a, b) => a + b, 0) / xs.length
        const cy = ys.reduce((a, b) => a + b, 0) / ys.length

        const { distance, terrain } = getDistanceBetween(fromId, toId)
        setTravelLegs((prev) => [
          ...prev,
          { distance: String(distance), terrain, to_location_id: toId, travel_type: 'normal' },
        ])
        setDraft((d) => [...d, [cx, cy]])
      }
      return
    }

    if (tool === 'ruler') {
      if (r.polygon.length > 0) {
        const xs = r.polygon.map((p) => p[0])
        const ys = r.polygon.map((p) => p[1])
        const cx = xs.reduce((a, b) => a + b, 0) / xs.length
        const cy = ys.reduce((a, b) => a + b, 0) / ys.length
        setDraft((d) => [...d, [cx, cy]])
      }
      return
    }

    if (edit) {
      if (confirm(`Delete region “${r.name ?? 'unnamed'}”?`)) deleteRegion.mutate(r.id)
      return
    }
    if (r.child_map_id && r.child_map_name) onDrill(r.child_map_id, r.child_map_name)
    else if (r.target_entity_id) openPeek(r.target_entity_id)
  }

  const onMapClick = (x: number, y: number) => {
    if (tool === 'ruler') {
      if (!travelMode) {
        setDraft((d) => [...d, [x, y]])
      }
      return
    }
    if (!edit) return
    if (tool === 'pin') setPending({ x, y })
    else setDraft((d) => [...d, [x, y]])
  }

  const onMarkerMove = (marker: MapMarker, x: number, y: number) => {
    if (!edit) return
    updateMarker.mutate({ markerId: marker.id, patch: { x, y } })
  }

  const onPartyMove = (x: number, y: number) => {
    patchParty.mutate({
      current_map_id: detail.entity_id,
      current_x: x,
      current_y: y,
      coordinates_set: true,
      current_location_id: null,
      location_set: true,
    })
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
      <DepictsLocation
        campaignId={campaignId}
        mapId={detail.entity_id}
        locationId={detail.location_id ?? null}
      />

      <MapDescription
        campaignId={campaignId}
        mapId={detail.entity_id}
        description={detail.description ?? null}
      />

      <div className="row" style={{ gap: 8, marginBottom: 8, alignItems: 'center' }}>
        <button
          className={tool === 'ruler' && !travelMode ? '' : 'ghost'}
          onClick={() => {
            setTravelMode(false)
            switchTool(tool === 'ruler' && !travelMode ? 'pin' : 'ruler')
          }}
        >
          📏 Ruler / Measure
        </button>

        {party?.current_location_id && (
          <button
            className={travelMode ? '' : 'ghost'}
            onClick={() => {
              const active = !travelMode
              setTravelMode(active)
              if (active) {
                switchTool('ruler')
                const startMarker = detail.markers.find((k) => k.target_entity_id === party.current_location_id)
                if (startMarker) {
                  setDraft([[startMarker.x, startMarker.y]])
                }
                setTravelLegs([])
              } else {
                switchTool('pin')
              }
            }}
          >
            🧭 Route Travel Planner
          </button>
        )}

        {party && (
          <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>
            Party Position:{' '}
            {party.current_map_id === detail.entity_id ? (
              party.current_location_name ? (
                <span>📍 Snapped to {party.current_location_name}</span>
              ) : (
                <span>📍 Free coords ({Math.round(party.current_x ?? 0)}, {Math.round(party.current_y ?? 0)})</span>
              )
            ) : party.current_location_name ? (
              <span>At location: {party.current_location_name}</span>
            ) : (
              <span>Not on map / unplaced</span>
            )}
          </span>
        )}
      </div>

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
          scalePixelsPerUnit={detail.scale_pixels_per_unit}
          scaleUnit={detail.scale_unit}
          partyLocationId={party?.current_location_id}
          partyX={party?.current_map_id === detail.entity_id ? party.current_x : null}
          partyY={party?.current_map_id === detail.entity_id ? party.current_y : null}
          onPartyMove={onPartyMove}
        />
        {(edit || tool === 'ruler' || travelMode) && (
          <div className="map-side card" style={{ minWidth: travelMode ? '340px' : '260px' }}>
            {travelMode && campaign && (
              <div>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
                  <h3 style={{ margin: 0 }}>Route Planner</h3>
                  <button className="ghost tag-x" onClick={() => { setTravelLegs([]); setDraft([]); }}>Clear Route</button>
                </div>
                <p className="muted" style={{ fontSize: 11, marginBottom: 12 }}>
                  Click location pins sequentially to build your travel route.
                </p>
                <TravelPlanner
                  campaignId={campaignId}
                  systemId={campaign.rule_system_id}
                  legs={travelLegs}
                  onLegsChange={setTravelLegs}
                />
              </div>
            )}

            {!travelMode && tool === 'ruler' && (
              <RulerSidePanel
                campaignId={campaignId}
                detail={detail}
                draft={draft}
                onClear={() => setDraft([])}
                onCalibrate={(pxPerUnit, unit) => {
                  updateMap.mutate(
                    {
                      scale_pixels_per_unit: pxPerUnit,
                      scale_unit: unit,
                      scale_set: true,
                    },
                    {
                      onSuccess: () => {
                        switchTool('pin')
                      },
                    },
                  )
                }}
                onTravel={handleTravel}
              />
            )}

            {edit && tool !== 'ruler' && !travelMode && (
              <>
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
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}

export function DepictsLocation({
  campaignId,
  mapId,
  locationId,
}: {
  campaignId: string
  mapId: string
  locationId: string | null
}) {
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const setLocation = useSetMapLocation(campaignId)
  const [editing, setEditing] = useState(false)
  const owner = locations?.find((l) => l.id === locationId)

  const save = (value: string) => {
    setLocation.mutate({ mapId, locationId: value }, { onSuccess: () => setEditing(false) })
  }

  return (
    <div className="row" style={{ gap: 8, marginBottom: 8, alignItems: 'center' }}>
      <span className="muted" style={{ fontSize: 12 }}>Depicts</span>
      {editing ? (
        <>
          <select
            defaultValue={locationId ?? ''}
            onChange={(e) => save(e.target.value)}
            disabled={setLocation.isPending}
          >
            <option value="">— no location —</option>
            {locations?.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
          <button className="ghost" onClick={() => setEditing(false)}>Cancel</button>
        </>
      ) : (
        <>
          {owner ? (
            <Link to="/entities/$entityId" params={{ entityId: owner.id }}>{owner.name}</Link>
          ) : (
            <span className="muted">no location</span>
          )}
          <button className="ghost" onClick={() => setEditing(true)}>
            {owner ? 'Change' : 'Set location'}
          </button>
        </>
      )}
    </div>
  )
}

export function MapDescription({
  campaignId,
  mapId,
  description,
}: {
  campaignId: string
  mapId: string
  description: string | null
}) {
  const update = useUpdateMap(campaignId, mapId)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(description ?? '')

  const startEdit = () => {
    setText(description ?? '')
    setEditing(true)
  }
  const save = () => {
    update.mutate(
      { description: text.trim() || null, description_set: true },
      { onSuccess: () => setEditing(false) },
    )
  }

  if (editing) {
    return (
      <div className="card" style={{ marginBottom: 8 }}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          style={{ width: '100%' }}
          placeholder="Describe this place…"
          autoFocus
        />
        <div className="row" style={{ gap: 6, marginTop: 8 }}>
          <button disabled={update.isPending} onClick={save}>
            {update.isPending ? 'Saving…' : 'Save'}
          </button>
          <button className="ghost" onClick={() => setEditing(false)}>Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div className="card map-description" style={{ marginBottom: 8 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        {description ? (
          <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{description}</p>
        ) : (
          <p className="muted" style={{ margin: 0 }}>No description yet.</p>
        )}
        <button className="ghost" style={{ flexShrink: 0 }} onClick={startEdit}>
          {description ? 'Edit' : 'Add description'}
        </button>
      </div>
    </div>
  )
}

export function NewRegionForm({
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

export function NewMarkerForm({
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

export function RulerSidePanel({
  campaignId,
  detail,
  draft,
  onClear,
  onCalibrate,
  onTravel,
}: {
  campaignId: string
  detail: MapDetail
  draft: [number, number][]
  onClear: () => void
  onCalibrate: (pxPerUnit: number, unit: string) => void
  onTravel?: (distance: number, travelType: string) => void
}) {
  const [calValue, setCalValue] = useState('')
  const [calUnit, setCalUnit] = useState('mile')
  const [travelType, setTravelType] = useState('normal')
  const [previewPlan, setPreviewPlan] = useState<TravelPlan | null>(null)
  const [previewErr, setPreviewErr] = useState<string | null>(null)

  let pxLength = 0
  for (let i = 1; i < draft.length; i++) {
    const p1 = draft[i - 1]
    const p2 = draft[i]
    pxLength += Math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
  }

  const scale = detail.scale_pixels_per_unit
  const unit = detail.scale_unit ?? 'mile'
  const hasScale = scale && scale > 0
  
  const [showCalibrateForm, setShowCalibrateForm] = useState(!hasScale)
  
  useEffect(() => {
    setShowCalibrateForm(!hasScale)
  }, [hasScale])

  const gameDist = hasScale ? pxLength / scale : pxLength

  useEffect(() => {
    if (!hasScale || gameDist <= 0) {
      setPreviewPlan(null)
      return
    }

    const isForcedMarch = travelType === 'forced march'
    let active = true

    previewTravel(campaignId, [{
      distance: gameDist,
      terrain: 'road',
      travel_type: travelType,
    }], isForcedMarch)
      .then((data) => {
        if (active) {
          setPreviewPlan(data as unknown as TravelPlan)
          setPreviewErr(null)
        }
      })
      .catch((e: Error) => {
        if (active) {
          setPreviewErr(e.message)
          setPreviewPlan(null)
        }
      })

    return () => {
      active = false
    }
  }, [campaignId, gameDist, travelType, hasScale])

  const UNIT_LABELS: Record<string, string> = {
    mile: 'mi',
    km: 'km',
    m: 'm',
    foot: 'ft',
  }
  const displayUnit = hasScale ? (UNIT_LABELS[unit] ?? unit) : 'px'

  const handleCalibrate = (e: React.FormEvent) => {
    e.preventDefault()
    if (draft.length !== 2) return
    const num = Number(calValue)
    if (!num || num <= 0) return

    const p1 = draft[0]
    const p2 = draft[1]
    const distPx = Math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
    const pxPerUnit = distPx / num
    onCalibrate(pxPerUnit, calUnit)
    setCalValue('')
    setShowCalibrateForm(false)
  }

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Ruler Tool</h3>
      <p className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
        Click points on the map to measure distance. Click a pin or region to trace through hotspots.
      </p>

      <div className="card" style={{ padding: 8, marginBottom: 4 }}>
        <div style={{ fontSize: 11 }} className="muted">Total measured length</div>
        <div style={{ fontSize: 18, fontWeight: 'bold', margin: '4px 0' }}>
          {gameDist.toFixed(hasScale ? 2 : 0)} {displayUnit}
        </div>
      </div>

      {previewPlan && (
        <div className="card" style={{ padding: 8, marginTop: 4, marginBottom: 8, border: '1px dashed var(--accent, #e05252)' }}>
          <div style={{ fontSize: 11 }} className="muted">Estimated duration</div>
          <div style={{ fontSize: 16, fontWeight: 'bold', margin: '4px 0' }}>
            {hoursMinutes(previewPlan.total_seconds)}
          </div>
          {previewPlan.rest_stops > 0 && (
            <div style={{ fontSize: 10, color: 'var(--text-muted, #aaa)' }}>
              ({previewPlan.rest_stops} long rest(s) en route)
            </div>
          )}
          <div style={{ fontSize: 10, color: 'var(--text-muted, #aaa)', marginTop: 2 }}>
            Arrives: {previewPlan.arrive_at_label}
          </div>
        </div>
      )}
      {previewErr && (
        <div className="tag danger" style={{ marginTop: 4, marginBottom: 8, fontSize: 10 }}>
          {previewErr}
        </div>
      )}

      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12, alignItems: 'center' }}>
        {draft.length > 0 ? (
          <div className="row" style={{ gap: 6, alignItems: 'center' }}>
            <button className="ghost tag-x" style={{ fontSize: 11, padding: '2px 6px' }} onClick={onClear}>
              Clear
            </button>
            {hasScale && (
              <>
                <button
                  style={{ fontSize: 11, padding: '2px 6px' }}
                  onClick={() => onTravel?.(gameDist, travelType)}
                >
                  🧭 Travel
                </button>
                <select
                  style={{ fontSize: 11, padding: '2px', maxWidth: '105px' }}
                  value={travelType}
                  onChange={(e) => setTravelType(e.target.value)}
                  aria-label="travel type"
                >
                  <option value="normal">Normal (Foot)</option>
                  <option value="forced march">Forced March</option>
                  <option value="mounted">Mounted (Horse)</option>
                  <option value="gallop difficult terrain">Gallop + Diff</option>
                  <option value="slow (sneak)">Slow (Sneak)</option>
                  <option value="mounted difficult terrain">Mounted + Diff</option>
                  <option value="difficult terrain">Difficult (Foot)</option>
                </select>
              </>
            )}
          </div>
        ) : <span />}

        {hasScale && (
          <button
            className="ghost"
            style={{ fontSize: 11, padding: '2px 6px' }}
            onClick={() => {
              alert("Click exactly two points on the map to define the new scale distance.");
              onClear();
              setShowCalibrateForm(true);
            }}
          >
            ✏️ Recalibrate
          </button>
        )}
      </div>

      {draft.length > 0 && hasScale && (
        <div style={{ marginTop: -6, marginBottom: 12, padding: '6px 8px', background: 'var(--bg-light, rgba(255,255,255,0.05))', borderRadius: 4, fontSize: 10, color: 'var(--text-muted, #aaa)', lineHeight: 1.3 }}>
          💡 {RULES_HELP[travelType] || RULES_HELP.normal}
        </div>
      )}

      {showCalibrateForm && draft.length === 2 && (
        <form onSubmit={handleCalibrate} className="card" style={{ padding: 8, marginTop: 8 }}>
          <h4 style={{ margin: '0 0 4px 0', fontSize: 12 }}>Calibrate Map Scale</h4>
          <div className="muted" style={{ fontSize: 10, marginBottom: 6 }}>
            Set real distance for the drawn 2-point line:
          </div>
          <div className="row" style={{ gap: 4 }}>
            <input
              placeholder="e.g. 5"
              style={{ width: '50px', padding: '2px 4px', fontSize: 11 }}
              value={calValue}
              onChange={(e) => setCalValue(e.target.value)}
            />
            <select
              style={{ padding: '2px', fontSize: 11 }}
              value={calUnit}
              onChange={(e) => setCalUnit(e.target.value)}
            >
              <option value="mile">mile(s)</option>
              <option value="km">km</option>
              <option value="m">m</option>
              <option value="foot">foot/feet</option>
            </select>
            <button type="submit" style={{ padding: '2px 4px', fontSize: 11 }}>
              Set Scale
            </button>
          </div>
        </form>
      )}

      {showCalibrateForm && draft.length !== 2 && (
        <div className="tag info" style={{ marginTop: 8, display: 'block', fontSize: 10 }}>
          💡 Click exactly two points on the map to define the new scale line.
        </div>
      )}

      {hasScale ? (
        <div className="muted" style={{ fontSize: 10, marginTop: 8 }}>
          Current map scale: 1 {UNIT_LABELS[unit] ?? unit} = {scale.toFixed(1)} px
        </div>
      ) : (
        <div className="tag warning" style={{ marginTop: 12, display: 'block', fontSize: 11, lineHeight: '1.4' }}>
          ⚠️ <strong>Map scale is not calibrated!</strong><br />
          Please click exactly <strong>two points</strong> on the map, then enter the distance between them above to set the permanent scale.
        </div>
      )}
    </div>
  )
}
