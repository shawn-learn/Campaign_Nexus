import { render, cleanup, fireEvent, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapSummary } from '../../api/client'

// Covers the wiring the card adds: filtering maps by location_id, the attach picker
// (including the "owned elsewhere" label), and the detach sentinel (`location_id: ''`,
// because the backend reads null as "field not provided"). Leaflet cannot run in jsdom,
// so the map canvas is mocked to a marker div; the map detail payload is faked.
vi.mock('../atlas/LeafletMap', () => ({
  LeafletMap: (props: { imageUrl: string }) => (
    <div data-testid="leaflet" data-image={props.imageUrl} />
  ),
}))

const setLocationMutate = vi.fn()
let mapsData: MapSummary[] | undefined

vi.mock('../../api/hooks', () => ({
  useMaps: () => ({ data: mapsData }),
  useMap: (_cid: string | null, mapId: string | null) => ({
    data: mapId
      ? { entity_id: mapId, width_px: 100, height_px: 80, markers: [], regions: [], layers: [] }
      : undefined,
  }),
  useEntities: () => ({
    data: [{ id: 'loc-other', name: 'Vallaki', entity_type: 'location' }],
  }),
  useSetMapLocation: () => ({ mutate: setLocationMutate, isPending: false }),
  useParty: () => ({ data: undefined }),
  usePatchParty: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))

import { LocationMapCard } from './LocationMapCard'

function summary(over: Partial<MapSummary>): MapSummary {
  return {
    entity_id: 'map1', name: 'Map of Barovia', description: null, map_kind: 'region',
    width_px: 100, height_px: 80, location_id: null, parent_map_id: null, marker_count: 0,
    ...over,
  } as MapSummary
}

beforeEach(() => {
  vi.clearAllMocks()
  mapsData = undefined
})
afterEach(cleanup)

describe('LocationMapCard', () => {
  it('renders the attached map and no picker prompt when a map depicts this location', () => {
    mapsData = [summary({ location_id: 'loc1' })]
    const ui = within(render(<LocationMapCard campaignId="c1" entityId="loc1" />).container)

    const map = ui.getByTestId('leaflet')
    expect(map.dataset.image).toBe('/api/v1/campaigns/c1/maps/map1/image')
    expect(ui.queryByText(/no map attached/i)).not.toBeInTheDocument()
    expect(ui.getByText(/open in atlas/i)).toBeInTheDocument()
  })

  it('shows the attach picker when no map is attached, labeling maps owned elsewhere', () => {
    mapsData = [
      summary({ entity_id: 'map1', name: 'Free Map' }),
      summary({ entity_id: 'map2', name: 'Vallaki Map', location_id: 'loc-other' }),
    ]
    const ui = within(render(<LocationMapCard campaignId="c1" entityId="loc1" />).container)

    expect(ui.getByText(/no map attached/i)).toBeInTheDocument()
    fireEvent.click(ui.getByRole('button', { name: /attach a map/i }))

    expect(ui.getByRole('option', { name: /Free Map \(region\)$/ })).toBeInTheDocument()
    expect(
      ui.getByRole('option', { name: /Vallaki Map \(region\) — currently at Vallaki/ }),
    ).toBeInTheDocument()

    fireEvent.change(ui.getByRole('combobox'), { target: { value: 'map1' } })
    fireEvent.click(ui.getByRole('button', { name: /^attach$/i }))
    expect(setLocationMutate).toHaveBeenCalledWith(
      { mapId: 'map1', locationId: 'loc1' },
      expect.anything(),
    )
  })

  it('detaches with the empty-string sentinel (null would be a backend no-op)', () => {
    mapsData = [summary({ location_id: 'loc1' })]
    const ui = within(render(<LocationMapCard campaignId="c1" entityId="loc1" />).container)

    fireEvent.click(ui.getByRole('button', { name: /detach/i }))
    expect(setLocationMutate).toHaveBeenCalledWith({ mapId: 'map1', locationId: '' })
  })

  it('offers chips to switch between multiple attached maps', () => {
    mapsData = [
      summary({ entity_id: 'map1', name: 'Region Map', location_id: 'loc1' }),
      summary({ entity_id: 'map2', name: 'City Map', location_id: 'loc1' }),
    ]
    const ui = within(render(<LocationMapCard campaignId="c1" entityId="loc1" />).container)

    // First attached map selected by default.
    expect(ui.getByTestId('leaflet').dataset.image).toContain('map1')
    fireEvent.click(ui.getByRole('button', { name: 'City Map' }))
    expect(ui.getByTestId('leaflet').dataset.image).toContain('map2')
  })

  it('renders nothing while the map list is loading', () => {
    mapsData = undefined
    const { container } = render(<LocationMapCard campaignId="c1" entityId="loc1" />)
    expect(container).toBeEmptyDOMElement()
  })
})
