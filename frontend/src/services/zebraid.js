// Typed-by-convention wrappers for the /api/v1 business endpoints (see backend/docs/API.md).
// All calls go through the shared `apiV1` Axios client, so failures reject with the
// normalised ApiError from api.js ({message, status, code, details, requestId}).
import { apiV1 } from './api.js'

const data = (r) => r.data

/** Seconds a signed image URL stays valid for page display (backend max 3600). */
export const IMAGE_URL_TTL = 900
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const ZEBRA_STATUSES = ['active', 'inactive', 'deceased']
export const FLANK_SIDES = ['unknown', 'left', 'right']

// Drop undefined/empty params so they are not sent as "?x=".
const clean = (params) =>
  Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== ''))

export const zebrasApi = {
  /** params: search, status, species, sex, sort ('code' | '-created_at'), limit, offset */
  list: (params) => apiV1.get('/zebras', { params: clean(params) }).then(data),
  get: (id) => apiV1.get(`/zebras/${id}`).then(data),
  /** body: {code, name?, species?, sex?, status?, notes?, attributes?} */
  create: (body) => apiV1.post('/zebras', body).then(data),
  /** body: any of {name, species, sex, status, notes, attributes}; code is immutable */
  update: (id, body) => apiV1.patch(`/zebras/${id}`, body).then(data),
  remove: (id) => apiV1.delete(`/zebras/${id}`),
}

export const imagesApi = {
  list: (params) => apiV1.get('/images', { params: clean(params) }).then(data),
  get: (id) => apiV1.get(`/images/${id}`).then(data),
  url: (id, expiresIn = IMAGE_URL_TTL) => apiV1.get(`/images/${id}/url`, { params: { expires_in: expiresIn } }).then(data),
  /**
   * Multipart upload. fields: kind (query|reference|crop), uploaded_by?, captured_at?, metadata? (object),
   * crop only: sourceImageId + cropBbox {x, y, width, height} in source pixels.
   */
  upload: (file, { kind, uploadedBy, capturedAt, metadata, sourceImageId, cropBbox } = {}, onUploadProgress) => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    if (sourceImageId) form.append('source_image_id', sourceImageId)
    if (cropBbox) form.append('crop_bbox', JSON.stringify(cropBbox))
    if (uploadedBy) form.append('uploaded_by', uploadedBy)
    if (capturedAt) form.append('captured_at', capturedAt)
    if (metadata && Object.keys(metadata).length) form.append('metadata', JSON.stringify(metadata))
    return apiV1.post('/images', form, { onUploadProgress, timeout: 120000 }).then(data)
  },
  remove: (id) => apiV1.delete(`/images/${id}`),
}

export const galleryApi = {
  /** params: include_inactive, include_urls, expires_in, limit, offset */
  list: (zebraId, params) => apiV1.get(`/zebras/${zebraId}/gallery`, { params: clean(params) }).then(data),
  /** body: {image_asset_id, side?, quality_notes?, registered_by?, metadata?} */
  add: (zebraId, body) => apiV1.post(`/zebras/${zebraId}/gallery`, body).then(data),
  remove: (entryId) => apiV1.delete(`/gallery/${entryId}`),
}

export const sightingsApi = {
  /** params: zebra_id, unidentified_only, since, until, location_name, min_lat, max_lat, min_lon, max_lon, limit, offset */
  list: (params) => apiV1.get('/sightings', { params: clean(params) }).then(data),
  get: (id) => apiV1.get(`/sightings/${id}`).then(data),
  /** body: SightingCreate {observed_at, zebra_id?, image_asset_id?, identification_run_id?, latitude?, longitude?, location_name?, observer?, notes?} */
  create: (body) => apiV1.post('/sightings', body).then(data),
  /** body: SightingUpdate. image_asset_id cannot be changed after creation (backend schema). */
  update: (id, body) => apiV1.patch(`/sightings/${id}`, body).then(data),
  remove: (id) => apiV1.delete(`/sightings/${id}`),
}

export const identificationsApi = {
  list: (params) => apiV1.get('/identifications', { params: clean(params) }).then(data),
}

/**
 * Upload a reference photo and register it in a zebra's gallery.
 * If the gallery link fails, the just-uploaded image is deleted again so no
 * unattached reference image is left behind.
 */
export async function addReferencePhoto(zebraId, file, { side = 'unknown', qualityNotes } = {}, onUploadProgress) {
  const image = await imagesApi.upload(file, { kind: 'reference' }, onUploadProgress)
  try {
    return await galleryApi.add(zebraId, { image_asset_id: image.id, side, quality_notes: qualityNotes || undefined })
  } catch (err) {
    await imagesApi.remove(image.id).catch(() => {})
    throw err
  }
}

/** Client-side pre-check; the backend re-validates the actual bytes. Returns an error message or null. */
export function checkImageFile(file) {
  if (!file) return 'Choose a photograph'
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) return 'Use a JPEG, PNG or WebP image'
  if (file.size > MAX_UPLOAD_BYTES) return 'Image is larger than 10 MB'
  if (file.size === 0) return 'File is empty'
  return null
}
