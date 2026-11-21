// Scientific stripe-analysis API adapter (Member 1 morphology + Member 2 spatial frequency).
// Connects exclusively to /api/v1/analyses/* endpoints; never invents measurements.
import { PINNED_COMMITS } from '../lib/analysisResults.js'
import { apiV1 } from './api.js'

const data = (r) => r.data

let capabilityPromise = null

const FALLBACK_UNAVAILABLE = (reason) => ({
  stripe_morphology: { available: false, reason, source_commit: PINNED_COMMITS.stripe_morphology, schema_version: '1.0.0' },
  spatial_frequency: { available: false, reason, source_commit: PINNED_COMMITS.spatial_frequency, schema_version: 'stripecode.science.v1' },
  limits: { max_pixels: 4000000, max_source_pixels: 12000000, max_dimension: 8192, queue_limit: 3, timeout_seconds: 120 },
})

export function getAnalysisCapability({ refresh = false } = {}) {
  if (!capabilityPromise || refresh) {
    capabilityPromise = apiV1
      .get('/analyses/capabilities', { params: refresh ? { refresh: true } : undefined })
      .then(data)
      .catch((err) => {
        capabilityPromise = null
        return FALLBACK_UNAVAILABLE(err.message || 'Could not reach the analysis service.')
      })
  }
  return capabilityPromise
}

export function submitMorphology(imageId, roi = null, config = {}) {
  const body = { image_id: imageId }
  if (roi) body.roi = roi
  if (config && Object.keys(config).length > 0) body.config = config
  return apiV1.post('/analyses/stripe-morphology', body).then(data)
}

export function submitFrequency(imageId, roi = null, options = {}) {
  const body = { image_id: imageId }
  if (roi) body.roi = roi
  if (options && Object.keys(options).length > 0) body.options = options
  return apiV1.post('/analyses/spatial-frequency', body).then(data)
}

/**
 * Submit Member 1 morphology + Member 2 spatial frequency as ONE request
 * (POST /api/v1/analyses/combined). The backend validates the shared ROI for both modules and
 * reserves queue capacity for both jobs atomically, so a pair is never half-submitted.
 * Resolves to `{ morphology, frequency, roiSemanticsNote, errors: [] }`; rejects with the API error.
 */
export async function submitCombinedAnalysis(imageId, roi = null, { morphologyConfig = {}, frequencyOptions = {} } = {}) {
  const body = { image_id: imageId }
  if (roi) body.roi = roi
  if (morphologyConfig && Object.keys(morphologyConfig).length > 0) body.morphology_config = morphologyConfig
  if (frequencyOptions && Object.keys(frequencyOptions).length > 0) body.frequency_options = frequencyOptions
  const res = await apiV1.post('/analyses/combined', body).then(data)
  return {
    morphology: res.stripe_morphology,
    frequency: res.spatial_frequency,
    roiSemanticsNote: res.roi_semantics_note,
    errors: [],
  }
}

export const getAnalysis = (id) => apiV1.get(`/analyses/${id}`).then(data)

export function listAnalyses(params = {}) {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
  return apiV1.get('/analyses', { params: clean }).then(data)
}

export const getArtifactUrl = (id, name, expiresIn = 600) =>
  apiV1.get(`/analyses/${id}/artifacts/${encodeURIComponent(name)}/url`, { params: { expires_in: expiresIn } }).then(data)

export const deleteAnalysis = (id) => apiV1.delete(`/analyses/${id}`)

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(Object.assign(new Error('Polling cancelled'), { name: 'AbortError' }))
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort() {
      clearTimeout(timer)
      reject(Object.assign(new Error('Polling cancelled'), { name: 'AbortError' }))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function waitWhileHidden(signal) {
  if (typeof document === 'undefined' || !document.hidden) return Promise.resolve()
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(Object.assign(new Error('Polling cancelled'), { name: 'AbortError' }))
    function onVis() {
      if (!document.hidden) {
        document.removeEventListener('visibilitychange', onVis)
        signal?.removeEventListener('abort', onAbort)
        resolve()
      }
    }
    function onAbort() {
      document.removeEventListener('visibilitychange', onVis)
      reject(Object.assign(new Error('Polling cancelled'), { name: 'AbortError' }))
    }
    document.addEventListener('visibilitychange', onVis)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * Poll GET /api/v1/analyses/{id} with exponential backoff (1s -> x1.5 up to 5s).
 * Pauses while the browser tab is hidden; stops on completed/failed, abort, or deadline.
 */
export async function waitForAnalysis(id, { signal, onUpdate, timeoutSeconds = 120 } = {}) {
  const deadline = Date.now() + (timeoutSeconds + 30) * 1000
  let delay = 1000
  while (Date.now() < deadline) {
    await waitWhileHidden(signal)
    const job = await getAnalysis(id)
    onUpdate?.(job)
    if (job.status === 'completed' || job.status === 'failed') return job
    await sleep(delay, signal)
    delay = Math.min(5000, Math.round(delay * 1.5))
  }
  throw Object.assign(new Error('Timed out waiting for analysis results. Refresh history shortly.'), { code: 'poll_timeout' })
}

export function friendlyAnalysisError(err) {
  if (err?.code === 'analysis_busy') return 'Analysis queue is full — try again shortly.'
  if (err?.code === 'analysis_limit_exceeded') return err.message || 'Image or region exceeds the analysis pixel limit.'
  if (err?.code === 'analysis_unavailable') return err.message || 'Scientific analysis service is currently unavailable.'
  if (err?.code === 'network_error') return 'Could not reach the STRIPEFORGE backend. Check that the API server is running.'
  return err?.message || 'Analysis request failed.'
}
