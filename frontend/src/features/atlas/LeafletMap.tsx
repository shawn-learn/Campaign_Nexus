import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { MapMarker, MapRegion } from '../../api/client'
import { imageSpaceToLeaflet, leafletToImageSpace } from './mapGeometry'

// A Leaflet CRS.Simple viewer: the image's pixel grid *is* the coordinate system, so a
// 12k×12k map pans/zooms at 60fps without a tile pyramid (docs/09 §11.2, FR-3.1). Markers
// and region polygons carry pixel coords with y measured from the top of the image (the
// natural export space); we convert to/from Leaflet's bottom-left origin here.
export type MapTool = 'pin' | 'region'

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
  /** Vertices placed so far while drawing a region, in image space. */
  draft: [number, number][]
  onMapClick: (x: number, y: number) => void
  onMarkerClick: (marker: MapMarker) => void
  onRegionClick: (region: MapRegion) => void
  onMarkerMove?: (marker: MapMarker, x: number, y: number) => void
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
}: Props) {
  const elRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  // Regions sit under the pins so a polygon never swallows a marker's click.
  const shapeRef = useRef<L.LayerGroup | null>(null)
  const pinRef = useRef<L.LayerGroup | null>(null)
  const draftRef = useRef<L.LayerGroup | null>(null)
  // Latest callbacks/flags without re-initializing the map instance on every render.
  const clickRef = useRef(onMapClick)
  const markerClickRef = useRef(onMarkerClick)
  const regionClickRef = useRef(onRegionClick)
  const markerMoveRef = useRef(onMarkerMove)
  clickRef.current = onMapClick
  markerClickRef.current = onMarkerClick
  regionClickRef.current = onRegionClick
  markerMoveRef.current = onMarkerMove

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
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      shapeRef.current = pinRef.current = draftRef.current = null
    }
  }, [imageUrl, width, height])

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

  // The in-progress polygon: vertices + the open chain between them.
  useEffect(() => {
    const layer = draftRef.current
    if (!layer) return
    layer.clearLayers()
    if (!editMode || tool !== 'region' || draft.length === 0) return
    const latlngs = draft.map(([x, y]) => L.latLng(height - y, x))
    L.polyline(latlngs, { color: '#9b8cff', weight: 2, dashArray: '4 4' }).addTo(layer)
    for (const ll of latlngs) {
      L.circleMarker(ll, { radius: 4, color: '#9b8cff', fillOpacity: 1 }).addTo(layer)
    }
  }, [draft, editMode, tool, height])

  // The dynamic class lives on the wrapper, never on the div Leaflet owns — otherwise a
  // React re-render would reset className and wipe Leaflet's own classes off the element.
  return (
    <div className={`leaflet-wrap ${editMode ? 'edit' : ''}`}>
      <div ref={elRef} className="leaflet-host" />
    </div>
  )
}
