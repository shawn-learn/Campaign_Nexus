import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { MapMarker, MapRegion } from '../../api/client'
import { imageSpaceToLeaflet, leafletToImageSpace } from './mapGeometry'

// A Leaflet CRS.Simple viewer: the image's pixel grid *is* the coordinate system, so a
// 12k×12k map pans/zooms at 60fps without a tile pyramid (docs/09 §11.2, FR-3.1). Markers
// and region polygons carry pixel coords with y measured from the top of the image (the
// natural export space); we convert to/from Leaflet's bottom-left origin here.
export type MapTool = 'pin' | 'region' | 'ruler'

interface Props {
  imageUrl: string
  width: number
  height: number
  markers: MapMarker[]
  regions: MapRegion[]
  /** Layers the GM has switched off; their markers and regions are not drawn. */
  hiddenLayers: string[]
  editMode: boolean
  tool: MapTool
  /** Vertices placed so far while drawing a region/ruler, in image space. */
  draft: [number, number][]
  onMapClick: (x: number, y: number) => void
  onMarkerClick: (marker: MapMarker) => void
  onRegionClick: (region: MapRegion) => void
  onMarkerMove?: (marker: MapMarker, x: number, y: number) => void
  scalePixelsPerUnit?: number | null
  scaleUnit?: string | null
  partyLocationId?: string | null
  partyX?: number | null
  partyY?: number | null
  onPartyMove?: (x: number, y: number) => void
}

const TYPE_COLOR: Record<string, string> = {
  npc: '#e0b64e',
  location: '#5aa6e0',
  faction: '#c65f9e',
  quest: '#6fce7a',
  encounter: '#e0603a',
  map: '#9b8cff',
}

function targetColor(
  color: string | null | undefined,
  targetType: string | null | undefined,
  childMapId: string | null | undefined,
): string {
  return color ?? (targetType ? TYPE_COLOR[targetType] : null) ??
    (childMapId ? TYPE_COLOR.map : '#cfcfcf')
}

function pinIcon(marker: MapMarker): L.DivIcon {
  const color = targetColor(marker.color, marker.target_type, marker.child_map_id)
  const ring = marker.child_map_id ? 'box-shadow:0 0 0 3px rgba(155,140,255,0.5);' : ''
  return L.divIcon({
    className: 'map-pin-wrap',
    html: `<span class="map-pin" style="background:${color};${ring}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })
}

export function LeafletMap({
  imageUrl,
  width,
  height,
  markers,
  regions,
  hiddenLayers,
  editMode,
  tool,
  draft,
  onMapClick,
  onMarkerClick,
  onRegionClick,
  onMarkerMove,
  scalePixelsPerUnit,
  scaleUnit,
  partyLocationId,
  partyX,
  partyY,
  onPartyMove,
}: Props) {
  const elRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  // Regions sit under the pins so a polygon never swallows a marker's click.
  const shapeRef = useRef<L.LayerGroup | null>(null)
  const pinRef = useRef<L.LayerGroup | null>(null)
  const draftRef = useRef<L.LayerGroup | null>(null)
  const partyRef = useRef<L.LayerGroup | null>(null)
  // Latest callbacks/flags without re-initializing the map instance on every render.
  const clickRef = useRef(onMapClick)
  const markerClickRef = useRef(onMarkerClick)
  const regionClickRef = useRef(onRegionClick)
  const markerMoveRef = useRef(onMarkerMove)
  const partyMoveRef = useRef(onPartyMove)
  clickRef.current = onMapClick
  markerClickRef.current = onMarkerClick
  regionClickRef.current = onRegionClick
  markerMoveRef.current = onMarkerMove
  partyMoveRef.current = onPartyMove

  // Initialize once per map image (bounds depend on width/height/url).
  useEffect(() => {
    if (!elRef.current) return
    const bounds = L.latLngBounds([0, 0], [height, width])
    const map = L.map(elRef.current, {
      crs: L.CRS.Simple,
      minZoom: -6,
      maxZoom: 4,
      zoomControl: true,
      attributionControl: false,
    })
    L.imageOverlay(imageUrl, bounds).addTo(map)
    map.fitBounds(bounds)
    map.on('click', (e: L.LeafletMouseEvent) => {
      clickRef.current(e.latlng.lng, height - e.latlng.lat)
    })
    shapeRef.current = L.layerGroup().addTo(map)
    pinRef.current = L.layerGroup().addTo(map)
    draftRef.current = L.layerGroup().addTo(map)
    partyRef.current = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      shapeRef.current = pinRef.current = draftRef.current = partyRef.current = null
    }
  }, [imageUrl, width, height])

  // Toggle map dragging and cursor style based on active tool.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const container = map.getContainer()
    if (tool === 'ruler' || (tool === 'region' && editMode)) {
      map.dragging.disable()
      container.style.cursor = 'crosshair'
    } else {
      map.dragging.enable()
      container.style.cursor = ''
    }
  }, [tool, editMode])

  // The edit sidebar resizes our container; tell Leaflet so tiles/overlay re-fit.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    // Wait for the CSS grid to reflow before measuring.
    const id = window.setTimeout(() => map.invalidateSize(), 50)
    return () => window.clearTimeout(id)
  }, [editMode])

  // Re-draw markers whenever they (or the layer filter) change.
  useEffect(() => {
    const layer = pinRef.current
    if (!layer) return
    layer.clearLayers()
    for (const m of markers) {
      if (hiddenLayers.includes(m.layer)) continue
      const pin = L.marker(imageSpaceToLeaflet(height, m.x, m.y), {
        icon: pinIcon(m),
        draggable: editMode,
      })
      const label = m.target_name ?? m.child_map_name ?? m.note ?? 'Marker'
      pin.bindTooltip(label, { direction: 'top', offset: [0, -8] })
      pin.on('click', (e: L.LeafletMouseEvent) => {
        L.DomEvent.stopPropagation(e)
        markerClickRef.current(m)
      })
      pin.on('dragend', (e: L.DragEndEvent) => {
        const { lat, lng } = e.target.getLatLng()
        const next = leafletToImageSpace(height, lat, lng)
        markerMoveRef.current?.(m, next.x, next.y)
      })
      pin.addTo(layer)
    }
  }, [markers, hiddenLayers, height, editMode])

  // Re-draw region polygons.
  useEffect(() => {
    const layer = shapeRef.current
    if (!layer) return
    layer.clearLayers()
    for (const r of regions) {
      if (hiddenLayers.includes(r.layer)) continue
      const color = targetColor(r.color, r.target_type, r.child_map_id)
      const poly = L.polygon(
        r.polygon.map(([x, y]) => L.latLng(height - y, x)),
        { color, weight: 2, fillOpacity: 0.18 },
      )
      const label = r.name ?? r.target_name ?? r.child_map_name ?? 'Region'
      poly.bindTooltip(label, { sticky: true })
      poly.on('click', (e: L.LeafletMouseEvent) => {
        L.DomEvent.stopPropagation(e)
        regionClickRef.current(r)
      })
      poly.addTo(layer)
    }
  }, [regions, hiddenLayers, height])

  // The in-progress polygon or ruler: vertices + the open chain between them.
  useEffect(() => {
    const layer = draftRef.current
    if (!layer) return
    layer.clearLayers()
    if (draft.length === 0) return
    if (tool === 'region' && !editMode) return

    const latlngs = draft.map(([x, y]) => L.latLng(height - y, x))
    const color = tool === 'ruler' ? '#ffd700' : '#9b8cff'
    
    L.polyline(latlngs, {
      color,
      weight: 3,
      dashArray: tool === 'ruler' ? '6 6' : '4 4',
    }).addTo(layer)

    let cumulativeDist = 0
    for (let i = 0; i < latlngs.length; i++) {
      const ll = latlngs[i]
      if (i > 0) {
        const p1 = draft[i - 1]
        const p2 = draft[i]
        const pixels = Math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
        if (scalePixelsPerUnit && scalePixelsPerUnit > 0) {
          cumulativeDist += pixels / scalePixelsPerUnit
        } else {
          cumulativeDist += pixels
        }
      }

      const circle = L.circleMarker(ll, {
        radius: 5,
        color,
        fillColor: '#fff',
        fillOpacity: 1,
        weight: 2,
      }).addTo(layer)

      const UNIT_LABELS: Record<string, string> = {
        mile: 'mi',
        km: 'km',
        m: 'm',
        foot: 'ft',
      }
      const unitLabel = scalePixelsPerUnit ? (UNIT_LABELS[scaleUnit ?? 'mile'] ?? scaleUnit ?? 'mi') : 'px'
      const label = i === 0 ? 'Start' : `${cumulativeDist.toFixed(1)} ${unitLabel}`
      
      circle.bindTooltip(label, {
        permanent: true,
        direction: 'top',
        offset: [0, -6],
        className: 'ruler-tooltip',
      })
    }
  }, [draft, editMode, tool, height, scalePixelsPerUnit, scaleUnit])

  // Re-draw party marker.
  useEffect(() => {
    const layer = partyRef.current
    const map = mapRef.current
    if (!layer || !map) return
    layer.clearLayers()

    let px = partyX
    let py = partyY

    // Fallback to location marker/region pin if free coordinates are not set
    if ((px === null || py === null || px === undefined || py === undefined) && partyLocationId) {
      const locMarker = markers.find((m) => m.target_entity_id === partyLocationId)
      if (locMarker) {
        px = locMarker.x
        py = locMarker.y
      } else {
        const locRegion = regions.find((r) => r.target_entity_id === partyLocationId)
        if (locRegion && locRegion.polygon.length > 0) {
          const xs = locRegion.polygon.map((p) => p[0])
          const ys = locRegion.polygon.map((p) => p[1])
          px = xs.reduce((a, b) => a + b, 0) / xs.length
          py = ys.reduce((a, b) => a + b, 0) / ys.length
        }
      }
    }

    if (px !== null && py !== null && px !== undefined && py !== undefined) {
      const pMarker = L.marker(imageSpaceToLeaflet(height, px, py), {
        icon: L.divIcon({
          className: 'map-party-wrap',
          html: `<span class="map-party" style="background:#ffd700;box-shadow:0 0 5px 3px rgba(255,215,0,0.5);border:2px solid #000;display:inline-block;width:24px;height:24px;border-radius:50%;text-align:center;line-height:22px;font-size:14px;font-weight:bold;z-index:9999;cursor:grab;">👑</span>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        }),
        draggable: true,
      })

      pMarker.bindTooltip('The Party', { direction: 'top', offset: [0, -12] })
      
      pMarker.on('dragend', (e: L.DragEndEvent) => {
        const { lat, lng } = e.target.getLatLng()
        const next = leafletToImageSpace(height, lat, lng)
        partyMoveRef.current?.(next.x, next.y)
      })

      pMarker.addTo(layer)
    }
  }, [partyX, partyY, partyLocationId, markers, regions, height])

  // The dynamic class lives on the wrapper, never on the div Leaflet owns — otherwise a
  // React re-render would reset className and wipe Leaflet's own classes off the element.
  return (
    <div className={`leaflet-wrap ${editMode ? 'edit' : ''}`}>
      <div ref={elRef} className="leaflet-host" />
    </div>
  )
}
