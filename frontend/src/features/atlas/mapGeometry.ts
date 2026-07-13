export function imageSpaceToLeaflet(height: number, x: number, y: number) {
  return { lat: height - y, lng: x }
}

export function leafletToImageSpace(height: number, lat: number, lng: number) {
  return { x: lng, y: height - lat }
}
