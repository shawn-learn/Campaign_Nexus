import { describe, expect, it } from 'vitest'
import { imageSpaceToLeaflet, leafletToImageSpace } from './mapGeometry'

describe('Atlas map geometry', () => {
  it('round-trips image-space coordinates through Leaflet coordinates', () => {
    const image = { x: 320, y: 180 }
    const leaflet = imageSpaceToLeaflet(400, image.x, image.y)

    expect(leaflet).toEqual({ lat: 220, lng: 320 })
    expect(leafletToImageSpace(400, leaflet.lat, leaflet.lng)).toEqual(image)
  })
})
