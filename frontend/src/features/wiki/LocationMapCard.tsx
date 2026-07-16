import { useEffect, useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useEntities, useMap, useMaps, useSetMapLocation, useParty, usePatchParty } from '../../api/hooks'
import { useUiStore } from '../../stores/ui'
import { LeafletMap } from '../atlas/LeafletMap'
import type { MapMarker, MapRegion, MapSummary } from '../../api/client'

// A location's map(s), embedded on its entity page (the atlas `Map.location_id` FK made
// visible). Read-only: pins peek their entity, drill-pins jump to the Atlas. The GM can
// attach/detach maps from here; the same association is editable from the map's Atlas page.
export function LocationMapCard({
  campaignId,
  entityId,
}: {
  campaignId: string
  entityId: string
}) {
  const { data: maps } = useMaps(campaignId)
  const setLocation = useSetMapLocation(campaignId)
  const { data: party } = useParty(campaignId)
  const patchParty = usePatchParty(campaignId)

  // location_id is not unique — a location may have several maps (region + city + dungeon).
  const attached = useMemo(
    () => (maps ?? []).filter((m) => m.location_id === entityId),
    [maps, entityId],
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const shownId =
    selectedId && attached.some((m) => m.entity_id === selectedId)
      ? selectedId
      : attached[0]?.entity_id ?? null

  const isPartyHere = party?.current_location_id === entityId

  // Reset the manual selection when it stops pointing at an attached map (e.g. detach).
  useEffect(() => {
    if (selectedId && !attached.some((m) => m.entity_id === selectedId)) setSelectedId(null)
  }, [attached, selectedId])

  if (maps === undefined) return null // still loading; don't flash the empty picker

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="row" style={{ gap: 10, alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>Map</h3>
          {party && (
            isPartyHere ? (
              <span className="tag success" style={{ fontSize: 11, padding: '2px 6px' }}>📍 Party is here</span>
            ) : (
              <button
                className="ghost"
                style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--border)' }}
                disabled={patchParty.isPending}
                onClick={() => patchParty.mutate({ current_location_id: entityId, location_set: true })}
              >
                📍 Move Party Here
              </button>
            )
          )}
        </div>
        {shownId && (
          <span className="row" style={{ gap: 6 }}>
            <Link to="/maps" search={{ open: shownId }}>Open in Atlas</Link>
            <button
              className="ghost"
              disabled={setLocation.isPending}
              // '' clears the FK — `null` would be read as "field not provided" (no-op).
              onClick={() => setLocation.mutate({ mapId: shownId, locationId: '' })}
            >
              Detach
            </button>
          </span>
        )}
      </div>

      {attached.length > 1 && (
        <div className="row layer-chips" style={{ gap: 6, margin: '8px 0' }}>
          {attached.map((m) => (
            <button
              key={m.entity_id}
              className={'chip' + (m.entity_id === shownId ? '' : ' off')}
              onClick={() => setSelectedId(m.entity_id)}
            >
              {m.name}
            </button>
          ))}
        </div>
      )}

      {shownId ? (
        <EmbeddedMap campaignId={campaignId} mapId={shownId} />
      ) : (
        <p className="muted" style={{ marginBottom: 8 }}>No map attached to this location.</p>
      )}

      <AttachPicker
        campaignId={campaignId}
        maps={maps}
        attached={attached}
        onAttach={(mapId) => {
          setLocation.mutate(
            { mapId, locationId: entityId },
            { onSuccess: () => setSelectedId(mapId) },
          )
        }}
        pending={setLocation.isPending}
      />
    </div>
  )
}

function EmbeddedMap({ campaignId, mapId }: { campaignId: string; mapId: string }) {
  const { data: detail } = useMap(campaignId, mapId)
  const openPeek = useUiStore((s) => s.openPeek)
  const imageUrl = `/api/v1/campaigns/${campaignId}/maps/${mapId}/image`

  // Play-mode semantics, same as the Atlas: pins peek their entity; drill-pins are shown
  // as a tooltip only (drilling happens in the Atlas — use "Open in Atlas" to explore).
  const onMarkerClick = (m: MapMarker) => {
    if (m.target_entity_id) openPeek(m.target_entity_id)
  }
  const onRegionClick = (r: MapRegion) => {
    if (r.target_entity_id) openPeek(r.target_entity_id)
  }

  // Leaflet must never mount into an unmeasured container — wait for the detail payload.
  if (!detail) return <p className="muted">Loading map…</p>

  return (
    <div className="location-map">
      <LeafletMap
        imageUrl={imageUrl}
        width={detail.width_px}
        height={detail.height_px}
        markers={detail.markers}
        regions={detail.regions ?? []}
        hiddenLayers={[]}
        editMode={false}
        tool="pin"
        draft={[]}
        onMapClick={() => {}}
        onMarkerClick={onMarkerClick}
        onRegionClick={onRegionClick}
      />
    </div>
  )
}

// Attach an existing map. Maps already depicting another location say whose in the option
// label — attaching one steals it (the FK is single-valued, last write wins).
function AttachPicker({
  campaignId,
  maps,
  attached,
  onAttach,
  pending,
}: {
  campaignId: string
  maps: MapSummary[]
  attached: MapSummary[]
  onAttach: (mapId: string) => void
  pending: boolean
}) {
  const [picking, setPicking] = useState(false)
  const [choice, setChoice] = useState('')
  // Owner names for "already attached elsewhere" labels; only fetched once the picker opens.
  const { data: locations } = useEntities(picking ? campaignId : null, { entity_type: 'location' })

  const attachedIds = new Set(attached.map((m) => m.entity_id))
  const candidates = maps.filter((m) => !attachedIds.has(m.entity_id))

  if (candidates.length === 0 && attached.length === 0) {
    return <p className="muted" style={{ fontSize: 12 }}>Upload maps in the Atlas first.</p>
  }
  if (candidates.length === 0) return null

  if (!picking) {
    return (
      <button className="ghost" onClick={() => setPicking(true)}>
        {attached.length > 0 ? '+ Attach another map' : 'Attach a map'}
      </button>
    )
  }

  const ownerLabel = (m: MapSummary) => {
    if (!m.location_id) return ''
    const owner = locations?.find((l) => l.id === m.location_id)?.name
    return owner ? ` — currently at ${owner}` : ' — attached elsewhere'
  }

  return (
    <form
      className="row"
      style={{ gap: 6 }}
      onSubmit={(e) => {
        e.preventDefault()
        if (!choice) return
        onAttach(choice)
        setPicking(false)
        setChoice('')
      }}
    >
      <select value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">— choose a map —</option>
        {candidates.map((m) => (
          <option key={m.entity_id} value={m.entity_id}>
            {m.name} ({m.map_kind}){ownerLabel(m)}
          </option>
        ))}
      </select>
      <button type="submit" disabled={!choice || pending}>Attach</button>
      <button type="button" className="ghost" onClick={() => setPicking(false)}>Cancel</button>
    </form>
  )
}
