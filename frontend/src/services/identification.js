// Identification adapter: the ONLY module the /identify UI talks to.
//
// Backend contract (verified against /openapi.json, Phase 3.2):
//   GET  /api/v1/identifications                       Page[IdentificationRunRead]
//   GET  /api/v1/identifications/{id}                  IdentificationRunDetail (run + candidates)
//   GET  /api/v1/identifications/{id}/candidates       CandidateRead[] ordered by rank
//   GET  /api/v1/identifications/{id}/verifications    VerificationRead[] oldest first (last = current)
//   POST /api/v1/identifications/{id}/verifications    VerificationSubmit -> VerificationRead
//     decision: 'confirmed' | 'rejected' | 'unknown'; verified_by required (1-120 chars);
//     confirmed/rejected need candidate_id of this run; unknown must not send one.
//
// There is NO inference/submission endpoint yet: the ML handoff contract has not
// been received. submitIdentification() therefore refuses with MlUnavailableError
// instead of guessing a URL or request body. When the backend gains the endpoint,
// implement `runInference` below against its real schema; capability detection
// already looks for it in the backend's OpenAPI document.
import { apiV1 } from './api.js'
import { checkImageFile, imagesApi, zebrasApi } from './zebraid.js'

export const DECISIONS = ['confirmed', 'rejected', 'unknown']
export const DEFAULT_TIMEOUT_MS = 20000

export class MlUnavailableError extends Error {
  constructor(reason) {
    super(reason)
    this.name = 'MlUnavailableError'
    this.code = 'ml_unavailable'
  }
}

/** Tag axios timeouts so the UI can say "timed out" instead of a raw message. */
function normalise(err) {
  if (err?.code === 'network_error' && /timeout/i.test(err.message || '')) {
    err.code = 'timeout'
    err.message = 'The server did not respond in time. Try again.'
  } else if (err?.code === 'network_error') {
    err.message = 'Cannot reach the ZebraID server. Check your connection.'
  }
  return err
}
const call = (promise) => promise.then((r) => r.data).catch((e) => Promise.reject(normalise(e)))

// -- capability -------------------------------------------------------------------
let capabilityPromise = null

/** Cold load of the 1.9 GB checkpoint (~75 s) + reference embedding can exceed a minute. */
export const IDENTIFY_TIMEOUT_MS = 300000

/**
 * GET /api/v1/identifications/capabilities ->
 * {available, reason, model_name, model_revision, checkpoint_sha256, preprocessing, device,
 *  gallery_cache_enabled, model_state: idle|loading|loaded|failed, model_load_seconds}
 */
export function getMlCapability({ refresh = false } = {}) {
  if (!capabilityPromise || refresh) {
    capabilityPromise = apiV1
      .get('/identifications/capabilities', { timeout: DEFAULT_TIMEOUT_MS })
      .then(({ data }) => data)
      .catch((e) => {
        capabilityPromise = null // retry next time
        return { available: false, reason: normalise(e).message || 'Could not reach the identification service.' }
      })
  }
  return capabilityPromise
}

/**
 * POST /api/v1/identifications {query_image_id, top_k} -> 201 IdentificationRunDetail
 * (MegaDescriptor-L-384 v1 on CPU against all active gallery reference images).
 */
async function runInference(queryImage, { topK = 5 } = {}) {
  return call(apiV1.post('/identifications', { query_image_id: queryImage.id, top_k: topK }, { timeout: IDENTIFY_TIMEOUT_MS }))
}

/**
 * Submit a photograph for identification:
 * capability check -> upload query image (POST /images, kind=query; identical bytes already
 * stored as a query image are reused) -> POST /identifications.
 */
export async function submitIdentification(file, { capturedAt, onUploadProgress, onUploaded, topK = 5 } = {}) {
  const problem = checkImageFile(file)
  if (problem) throw Object.assign(new Error(problem), { code: 'invalid_image' })
  const capability = await getMlCapability({ refresh: true })
  if (!capability.available) throw new MlUnavailableError(capability.reason)
  let queryImage
  try {
    queryImage = await imagesApi.upload(file, { kind: 'query', capturedAt }, onUploadProgress)
  } catch (e) {
    if (e?.code === 'duplicate_image' && e.details?.existing_image_id) queryImage = { id: e.details.existing_image_id }
    else throw normalise(e)
  }
  onUploaded?.(queryImage)
  return runInference(queryImage, { topK })
}

// -- runs, candidates, verifications -------------------------------------------------
export const listRuns = (params) => call(apiV1.get('/identifications', { params }))
export const getRun = (runId) => call(apiV1.get(`/identifications/${runId}`))
export const getCandidates = (runId) => call(apiV1.get(`/identifications/${runId}/candidates`))
export const getVerifications = (runId) => call(apiV1.get(`/identifications/${runId}/verifications`))

/** body: {decision, candidate_id?, verified_by, notes?} exactly as VerificationSubmit. */
export function submitVerification(runId, { decision, candidateId, verifiedBy, notes }) {
  const body = { decision, verified_by: verifiedBy }
  if (decision !== 'unknown') body.candidate_id = candidateId
  if (notes?.trim()) body.notes = notes.trim()
  return call(apiV1.post(`/identifications/${runId}/verifications`, body))
}

/** Current decision = latest row (append-only history). */
export const currentVerification = (verifications) => (verifications?.length ? verifications[verifications.length - 1] : null)

/** Latest decision recorded for a specific candidate, if any. */
export function candidateVerification(verifications, candidateId) {
  for (let i = (verifications?.length ?? 0) - 1; i >= 0; i--) {
    if (verifications[i].candidate_id === candidateId) return verifications[i]
  }
  return null
}

// -- lookups (cached per page load) ---------------------------------------------------
const zebraCache = new Map()
/** Zebra record for a candidate's zebra_id (cached). */
export function getZebra(zebraId) {
  if (!zebraCache.has(zebraId)) {
    zebraCache.set(
      zebraId,
      zebrasApi.get(zebraId).catch((e) => {
        zebraCache.delete(zebraId)
        throw normalise(e)
      }),
    )
  }
  return zebraCache.get(zebraId)
}

/** Short-lived signed URL for a stored image. */
export const getImageUrl = (imageId) => imagesApi.url(imageId).catch((e) => Promise.reject(normalise(e)))
