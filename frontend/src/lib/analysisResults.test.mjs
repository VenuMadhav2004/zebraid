import assert from 'node:assert/strict'
import test from 'node:test'
import {
  PINNED_COMMITS,
  describeFrequencyFilter,
  inferPairFromHistory,
  fmtMeasure,
  jobCommit,
  resolveDisplayedResults,
  retryRequest,
  sameImageAndRoi,
} from './analysisResults.js'

const roiA = { x: 0, y: 0, width: 512, height: 512 }
const roiB = { x: 32, y: 32, width: 256, height: 256 }
const job = (id, kind, extra = {}) => ({ id, kind, image_id: 'img-1', status: 'completed', roi: roiA, roi_mode: kind === 'stripe_morphology' ? 'mask' : 'box', ...extra })

test('pinned commits are the authoritative ones', () => {
  assert.equal(PINNED_COMMITS.stripe_morphology, '871e2956a3cda8d3fb08433a8450a3718e9e312f')
  assert.equal(PINNED_COMMITS.spatial_frequency, 'ff827ba826f4fa8e34acf3ba41528f91a0252c1e')
  assert.equal(jobCommit({}), null) // never substitutes a hash
})

test('same image and ROI comparison', () => {
  assert.equal(sameImageAndRoi(job('a', 'stripe_morphology'), job('b', 'spatial_frequency')), true)
  assert.equal(sameImageAndRoi(job('a', 'stripe_morphology'), job('b', 'spatial_frequency', { roi: roiB })), false)
  assert.equal(sameImageAndRoi(job('a', 'stripe_morphology'), job('b', 'spatial_frequency', { image_id: 'img-2' })), false)
})

test('combined view only for the submitted pair on the same image and ROI', () => {
  const m = job('m', 'stripe_morphology')
  const f = job('f', 'spatial_frequency')
  const pair = { morphologyId: 'm', frequencyId: 'f' }
  assert.deepEqual(resolveDisplayedResults({ selectedJob: m, pair, history: [m, f] }), { morphology: m, frequency: f, combined: true })
})

test('unrelated completed jobs are never merged into a combined view', () => {
  const m = job('m', 'stripe_morphology')
  const fOther = job('f2', 'spatial_frequency', { roi: roiB })
  const out = resolveDisplayedResults({ selectedJob: fOther, pair: null, history: [m, fOther] })
  assert.equal(out.combined, false)
  assert.equal(out.morphology, null)
  assert.equal(out.frequency, fOther)
})

test('pair with one job still running shows only the selected completed job', () => {
  const m = job('m', 'stripe_morphology')
  const f = job('f', 'spatial_frequency', { status: 'running' })
  const out = resolveDisplayedResults({ selectedJob: m, pair: { morphologyId: 'm', frequencyId: 'f' }, history: [m, f] })
  assert.deepEqual(out, { morphology: m, frequency: null, combined: false })
})

test('retry reuses the failed job image, ROI and parameters', () => {
  const failed = job('x', 'spatial_frequency', { status: 'failed', roi: roiB, parameters: { options: { filter_type: 'bandpass', cutoff_cpp: 0.12, band_low_cpp: 0.03 } } })
  assert.deepEqual(retryRequest(failed), { imageId: 'img-1', roi: roiB, kind: 'spatial_frequency', config: {}, options: failed.parameters.options })
  const auto = job('y', 'stripe_morphology', { status: 'failed', roi_mode: 'auto', parameters: { config: { clahe_clip_limit: 2 } } })
  assert.equal(retryRequest(auto).roi, null)
})

test('frequency filter description uses actual Member 2 keys', () => {
  assert.deepEqual(describeFrequencyFilter({ filter: 'gaussian', cutoff_cycles_per_pixel: 0.06, mode: 'exploratory' }), { type: 'gaussian', cutoff: '0.06 cycles/pixel' })
  assert.deepEqual(describeFrequencyFilter({ mode: 'image_space_bandpass', low_cycles_per_pixel: 0.03, high_cycles_per_pixel: 0.12 }), { type: 'bandpass', cutoff: '0.03–0.12 cycles/pixel' })
  assert.deepEqual(describeFrequencyFilter({}), { type: null, cutoff: null })
})

test('missing measurements are reported as unavailable', () => {
  assert.equal(fmtMeasure(undefined), 'unavailable')
  assert.equal(fmtMeasure(Number.NaN), 'unavailable')
  assert.equal(fmtMeasure(0.12345, 2), '0.12')
})

test('pair inference after reload requires same image/ROI and same submission time', () => {
  const t = '2026-11-21T10:00:00.000Z'
  const m = job('m', 'stripe_morphology', { created_at: t })
  const f = job('f', 'spatial_frequency', { created_at: '2026-11-21T10:00:00.015Z' })
  const fLater = job('f2', 'spatial_frequency', { created_at: '2026-11-21T10:05:00.000Z' })
  const fOtherRoi = job('f3', 'spatial_frequency', { roi: roiB, created_at: t })
  assert.deepEqual(inferPairFromHistory([m, f]), { morphologyId: 'm', frequencyId: 'f' })
  assert.equal(inferPairFromHistory([m, fLater]), null)
  assert.equal(inferPairFromHistory([m, fOtherRoi]), null)
})
