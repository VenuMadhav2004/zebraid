// Field rules mirror backend app/schemas/sighting.py (SightingCreate / SightingUpdate).
export const LIMITS = { location_name: 200, observer: 120 }

/** ISO timestamp -> value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null)

const num = (v) => (v === '' || v == null ? null : Number(v))

/** Returns {errors, coords: {latitude, longitude} | null}. */
export function validateSighting(values) {
  const errors = {}
  if (!values.observed_at) errors.observed_at = 'Required'
  else if (new Date(values.observed_at).getTime() > Date.now() + 5 * 60 * 1000) errors.observed_at = 'Observation time is in the future'

  const lat = num(values.latitude)
  const lon = num(values.longitude)
  if ((lat === null) !== (lon === null)) {
    errors[lat === null ? 'latitude' : 'longitude'] = 'Enter latitude and longitude together'
  }
  if (lat !== null && (!Number.isFinite(lat) || lat < -90 || lat > 90)) errors.latitude = 'Between -90 and 90'
  if (lon !== null && (!Number.isFinite(lon) || lon < -180 || lon > 180)) errors.longitude = 'Between -180 and 180'

  for (const f of ['location_name', 'observer']) {
    if ((values[f]?.trim().length ?? 0) > LIMITS[f]) errors[f] = `At most ${LIMITS[f]} characters`
  }
  return { errors, coords: lat !== null && lon !== null ? { latitude: lat, longitude: lon } : null }
}

export function formatCoords(lat, lon) {
  if (lat == null || lon == null) return null
  return `${Math.abs(lat).toFixed(5)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(5)}° ${lon >= 0 ? 'E' : 'W'}`
}
