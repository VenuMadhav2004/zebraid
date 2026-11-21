// Pure helpers for presenting scientific analysis jobs (no React, no network).
// Source of truth for field names: backend AnalysisJobRead + vendored Member 1 / Member 2 outputs.

/** Authoritative research commits (must match backend app/integrations/science/constants.py). */
export const PINNED_COMMITS = {
  stripe_morphology: '871e2956a3cda8d3fb08433a8450a3718e9e312f',
  spatial_frequency: 'ff827ba826f4fa8e34acf3ba41528f91a0252c1e',
}

export const shortCommit = (sha) => (typeof sha === 'string' && sha.length >= 7 ? sha.slice(0, 7) : 'unknown')

/** Commit actually recorded on a job; never substitutes a different hash. */
export function jobCommit(job) {
  return job?.provider?.source_commit || null
}

/** True when two jobs analysed the same stored image and the same canonical ROI rectangle. */
export function sameImageAndRoi(a, b) {
  if (!a || !b || a.image_id !== b.image_id) return false
  const ra = a.roi || {}
  const rb = b.roi || {}
  return ['x', 'y', 'width', 'height'].every((k) => Number.isInteger(ra[k]) && ra[k] === rb[k])
}

/**
 * Decide which completed jobs to show.
 * - A "combined" view is shown only for the two jobs created by one POST /analyses/combined
 *   submission (`pair`) and only if both are completed and share image + ROI.
 * - Otherwise only the selected completed job is shown (never a mix of unrelated runs).
 */
export function resolveDisplayedResults({ selectedJob, pair, history = [] }) {
  const byId = new Map(history.map((j) => [j.id, j]))
  const pairM = pair?.morphologyId ? byId.get(pair.morphologyId) : null
  const pairF = pair?.frequencyId ? byId.get(pair.frequencyId) : null
  const selectedInPair = Boolean(selectedJob && pair && (selectedJob.id === pair.morphologyId || selectedJob.id === pair.frequencyId))

  if ((!selectedJob || selectedInPair) && pairM?.status === 'completed' && pairF?.status === 'completed' && sameImageAndRoi(pairM, pairF)) {
    return { morphology: pairM, frequency: pairF, combined: true }
  }
  if (selectedJob?.status === 'completed') {
    return {
      morphology: selectedJob.kind === 'stripe_morphology' ? selectedJob : null,
      frequency: selectedJob.kind === 'spatial_frequency' ? selectedJob : null,
      combined: false,
    }
  }
  return { morphology: null, frequency: null, combined: false }
}

/**
 * Request needed to retry a job exactly: same image, same ROI (null when Member 1 ran in
 * library 'auto' mode, i.e. no ROI was supplied), same parameters.
 */
export function retryRequest(job) {
  if (!job) return null
  const roi = job.roi_mode === 'auto' ? null : job.roi ? { x: job.roi.x, y: job.roi.y, width: job.roi.width, height: job.roi.height } : null
  return {
    imageId: job.image_id,
    roi,
    kind: job.kind,
    config: job.parameters?.config || {},
    options: job.parameters?.options || {},
  }
}

/**
 * Describe the Member 2 filter from the actual result keys:
 * gaussian/butterworth -> filter.filter + filter.cutoff_cycles_per_pixel;
 * bandpass -> filter.mode 'image_space_bandpass' + low/high_cycles_per_pixel.
 */
export function describeFrequencyFilter(filter = {}) {
  if (filter.mode === 'image_space_bandpass') {
    return {
      type: 'bandpass',
      cutoff:
        Number.isFinite(filter.low_cycles_per_pixel) && Number.isFinite(filter.high_cycles_per_pixel)
          ? `${filter.low_cycles_per_pixel}–${filter.high_cycles_per_pixel} cycles/pixel`
          : null,
    }
  }
  return {
    type: typeof filter.filter === 'string' ? filter.filter : null,
    cutoff: Number.isFinite(filter.cutoff_cycles_per_pixel) ? `${filter.cutoff_cycles_per_pixel} cycles/pixel` : null,
  }
}

/** Format a number with fixed decimals; missing/non-finite values are reported as unavailable. */
export function fmtMeasure(v, digits = 3) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : 'unavailable'
}

/**
 * After a reload, recover the pair created by one POST /analyses/combined: both jobs are inserted
 * in the same database transaction, so they share image + ROI and their created_at values are
 * within milliseconds. Anything looser is not treated as a pair.
 */
export function inferPairFromHistory(history = [], maxGapMs = 2000) {
  for (const m of history) {
    if (m.kind !== 'stripe_morphology') continue
    const f = history.find(
      (j) =>
        j.kind === 'spatial_frequency' &&
        sameImageAndRoi(m, j) &&
        Math.abs(Date.parse(j.created_at) - Date.parse(m.created_at)) <= maxGapMs,
    )
    if (f) return { morphologyId: m.id, frequencyId: f.id }
  }
  return null
}
