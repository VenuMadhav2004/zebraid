import { useState } from 'react'
import { PINNED_COMMITS, shortCommit } from '../../lib/analysisResults.js'
import { cn } from '../../lib/cn.js'
import { Badge, Button, Card, Input, Select, Spinner } from '../ui/index.js'

const M1_DEFAULTS = {
  clahe_clip_limit: 3.0,
  adaptive_block_size: 51,
  min_stripe_area: 40,
  orientation_sigma: 3.0,
  min_branch_length: 15,
}

const M2_DEFAULTS = {
  filter_type: 'gaussian',
  cutoff_cpp: 0.06,
  band_low_cpp: 0.03,
}

const TABS = [
  ['stripe_morphology', 'Morphology'],
  ['spatial_frequency', 'Frequency'],
  ['combined', 'Combined'],
]

export default function AnalysisDrawer({
  source,
  naturalSize,
  roi,
  capability,
  refreshingCap,
  onRefreshCapability,
  activeJob,
  pollingElapsed,
  submitting,
  onSubmitMorphology,
  onSubmitFrequency,
  onSubmitCombined,
  onRetryJob,
  onStopPolling,
  onSaveCrop,
  cropBusy,
}) {
  const [tab, setTab] = useState('combined')
  const [m1, setM1] = useState(M1_DEFAULTS)
  const [m2, setM2] = useState(M2_DEFAULTS)

  const isLibrary = source?.type === 'library'
  const limits = capability?.limits ?? {
    max_pixels: 4000000,
    max_source_pixels: 12000000,
    max_dimension: 8192,
    queue_limit: 3,
    timeout_seconds: 120,
  }
  const m1Cap = capability?.stripe_morphology
  const m2Cap = capability?.spatial_frequency
  const available =
    tab === 'stripe_morphology'
      ? Boolean(m1Cap?.available)
      : tab === 'spatial_frequency'
        ? Boolean(m2Cap?.available)
        : Boolean(m1Cap?.available && m2Cap?.available)

  const unavailableReason =
    tab === 'stripe_morphology'
      ? m1Cap?.reason
      : tab === 'spatial_frequency'
        ? m2Cap?.reason
        : m1Cap?.reason || m2Cap?.reason

  const imagePixels = naturalSize ? naturalSize.width * naturalSize.height : 0
  const roiPixels = roi ? roi.width * roi.height : imagePixels
  // Data Contract §1: Member 1 analyses whole image; Member 2 crops to ROI.
  const analysedPixels = tab === 'spatial_frequency' ? roiPixels : imagePixels
  const overSourceLimit = naturalSize
    ? imagePixels > limits.max_source_pixels || Math.max(naturalSize.width, naturalSize.height) > limits.max_dimension
    : false
  const overAnalysedLimit = Boolean(naturalSize) && analysedPixels > limits.max_pixels
  const roiTooSmall = Boolean(roi && (roi.width < 16 || roi.height < 16))
  const bandpassInvalid =
    (tab === 'spatial_frequency' || tab === 'combined') &&
    m2.filter_type === 'bandpass' &&
    Number(m2.band_low_cpp) >= Number(m2.cutoff_cpp)

  const isRunning = activeJob && (activeJob.status === 'pending' || activeJob.status === 'running')

  function buildMorphologyConfig() {
    const changed = {}
    for (const [k, defVal] of Object.entries(M1_DEFAULTS)) {
      const val = Number(m1[k])
      if (Number.isFinite(val) && val !== defVal) changed[k] = val
    }
    return changed
  }

  function buildFrequencyOptions() {
    return {
      filter_type: m2.filter_type,
      cutoff_cpp: Number(m2.cutoff_cpp),
      band_low_cpp: Number(m2.band_low_cpp),
    }
  }

  function submit() {
    if (tab === 'stripe_morphology') {
      onSubmitMorphology(buildMorphologyConfig())
    } else if (tab === 'spatial_frequency') {
      onSubmitFrequency(buildFrequencyOptions())
    } else {
      onSubmitCombined({ morphologyConfig: buildMorphologyConfig(), frequencyOptions: buildFrequencyOptions() })
    }
  }

  const canSubmit =
    isLibrary &&
    Boolean(naturalSize) &&
    available &&
    !overSourceLimit &&
    !overAnalysedLimit &&
    !roiTooSmall &&
    !bandpassInvalid &&
    !submitting &&
    !isRunning

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Scientific analysis</h3>
        <div className="flex items-center gap-1.5">
          <Badge tone={available ? 'success' : 'warning'}>{available ? 'Ready' : 'Unavailable'}</Badge>
          {onRefreshCapability && (
            <button
              type="button"
              disabled={refreshingCap}
              onClick={onRefreshCapability}
              className="text-[0.6875rem] text-muted hover:text-ink underline disabled:opacity-40"
            >
              {refreshingCap ? 'Checking…' : 'Refresh'}
            </button>
          )}
        </div>
      </div>

      <div role="tablist" aria-label="Analysis mode" className="grid grid-cols-3 rounded-control border border-line bg-raised p-0.5 text-xs">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              'h-8 rounded-[0.375rem] px-1.5 font-medium transition-colors',
              tab === id ? 'bg-surface text-accent shadow-card' : 'text-muted hover:text-ink',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {!isLibrary ? (
        <p className="rounded-control border border-dashed border-line-strong bg-raised/50 px-3 py-2.5 text-xs text-muted">
          {source ? 'Save to image library to analyse stored pixel data privately.' : 'Open a stored image from the library to run scientific analysis.'}
        </p>
      ) : (
        <>
          <div className="rounded-control border border-line bg-raised/60 px-3 py-2 text-xs space-y-1">
            <div className="flex justify-between gap-2">
              <span className="text-faint">Target region</span>
              <span className="font-mono text-ink">
                {roi ? `${roi.width} × ${roi.height} at (${roi.x}, ${roi.y})` : 'Whole image'}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-faint">Analysed pixels</span>
              <span className={cn('tabular font-mono', overAnalysedLimit || overSourceLimit ? 'text-danger' : 'text-ink')}>
                {analysedPixels.toLocaleString()} / {limits.max_pixels.toLocaleString()}
              </span>
            </div>
            <p className="text-[0.6875rem] text-faint">
              {tab === 'stripe_morphology'
                ? 'Member 1 preprocesses the full image and restricts measurements to the pixel mask.'
                : tab === 'spatial_frequency'
                  ? 'Member 2 crops and analyses only the selected ROI box.'
                  : 'One request queues Member 1 (full-image mask) and Member 2 (ROI crop) on the same image and ROI; results are reported separately.'}
            </p>
          </div>

          {!available && (
            <div className="rounded-control border border-warning/30 bg-warning/10 px-3 py-2.5 text-xs text-muted space-y-1">
              <p className="font-medium text-warning">Analysis runtime unavailable</p>
              <p>{unavailableReason || 'Scientific modules are not active on this backend yet.'}</p>
              <p className="text-[0.6875rem] text-faint font-mono">
                Pinned commits: M1 {shortCommit(m1Cap?.source_commit || PINNED_COMMITS.stripe_morphology)} · M2{' '}
                {shortCommit(m2Cap?.source_commit || PINNED_COMMITS.spatial_frequency)}
              </p>
            </div>
          )}

          {(overSourceLimit || overAnalysedLimit) && (
            <div className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2.5 text-xs space-y-2">
              <p className="text-danger">
                Analysed area exceeds the {limits.max_pixels.toLocaleString()} px limit. Save a smaller crop to analyse at full pixel resolution.
              </p>
              {roi && onSaveCrop && (
                <Button size="sm" variant="secondary" className="w-full" loading={cropBusy} onClick={onSaveCrop}>
                  Save region as crop
                </Button>
              )}
            </div>
          )}

          {roiTooSmall && <p className="text-xs text-danger">Selected ROI must be at least 16 × 16 pixels.</p>}

          {(tab === 'stripe_morphology' || tab === 'combined') && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="eyebrow">Member 1 morphology config</span>
                <button type="button" onClick={() => setM1(M1_DEFAULTS)} className="text-[0.6875rem] text-muted hover:text-ink">
                  Reset defaults
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  label="CLAHE clip"
                  type="number"
                  step="0.5"
                  min="0.1"
                  value={m1.clahe_clip_limit}
                  onChange={(e) => setM1((s) => ({ ...s, clahe_clip_limit: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
                <Input
                  label="Block size"
                  type="number"
                  step="2"
                  min="3"
                  value={m1.adaptive_block_size}
                  onChange={(e) => setM1((s) => ({ ...s, adaptive_block_size: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
                <Input
                  label="Min stripe area"
                  type="number"
                  min="1"
                  value={m1.min_stripe_area}
                  onChange={(e) => setM1((s) => ({ ...s, min_stripe_area: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
                <Input
                  label="Orient. sigma"
                  type="number"
                  step="0.5"
                  min="0.1"
                  value={m1.orientation_sigma}
                  onChange={(e) => setM1((s) => ({ ...s, orientation_sigma: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
                <Input
                  label="Min branch len"
                  type="number"
                  min="1"
                  value={m1.min_branch_length}
                  onChange={(e) => setM1((s) => ({ ...s, min_branch_length: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
              </div>
            </div>
          )}

          {(tab === 'spatial_frequency' || tab === 'combined') && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="eyebrow">Member 2 frequency filter</span>
                <button type="button" onClick={() => setM2(M2_DEFAULTS)} className="text-[0.6875rem] text-muted hover:text-ink">
                  Reset defaults
                </button>
              </div>
              <Select
                label="Filter type"
                value={m2.filter_type}
                onChange={(e) => setM2((s) => ({ ...s, filter_type: e.target.value }))}
              >
                <option value="gaussian">Gaussian low-pass</option>
                <option value="butterworth">Butterworth low-pass</option>
                <option value="bandpass">Image-space band-pass</option>
              </Select>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  label={m2.filter_type === 'bandpass' ? 'High cutoff (cpp)' : 'Cutoff (cpp)'}
                  type="number"
                  step="0.01"
                  min="0.00001"
                  max="0.5"
                  value={m2.cutoff_cpp}
                  onChange={(e) => setM2((s) => ({ ...s, cutoff_cpp: e.target.value }))}
                  inputClassName="h-8 px-2 font-mono text-xs"
                />
                {m2.filter_type === 'bandpass' && (
                  <Input
                    label="Low cutoff (cpp)"
                    type="number"
                    step="0.01"
                    min="0.00001"
                    max="0.5"
                    value={m2.band_low_cpp}
                    onChange={(e) => setM2((s) => ({ ...s, band_low_cpp: e.target.value }))}
                    inputClassName="h-8 px-2 font-mono text-xs"
                  />
                )}
              </div>
              {bandpassInvalid && <p className="text-xs text-danger">Low cutoff must be strictly less than high cutoff.</p>}
            </div>
          )}

          {isRunning && (
            <div className="flex items-center justify-between gap-2 rounded-control border border-info/30 bg-info/10 px-3 py-2 text-xs">
              <div className="flex items-center gap-2 text-ink">
                <Spinner className="h-3.5 w-3.5 text-accent" />
                <span>
                  {activeJob.status === 'pending' ? 'Queued' : 'Running'} · {pollingElapsed}s
                </span>
              </div>
              <button type="button" onClick={onStopPolling} className="text-muted hover:text-ink underline">
                Stop waiting
              </button>
            </div>
          )}

          {activeJob?.status === 'failed' && (
            <div className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2.5 text-xs space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-danger">Analysis failed</span>
                {activeJob.error_code && <Badge tone="danger">{activeJob.error_code}</Badge>}
              </div>
              <p className="text-muted">{activeJob.error_message || 'The analysis did not complete.'}</p>
              {onRetryJob && available && (
                <Button size="sm" variant="secondary" className="w-full" disabled={submitting} onClick={() => onRetryJob(activeJob)}>
                  Retry analysis
                </Button>
              )}
            </div>
          )}

          <Button className="w-full" loading={submitting} disabled={!canSubmit} onClick={submit}>
            {tab === 'stripe_morphology'
              ? 'Run stripe morphology'
              : tab === 'spatial_frequency'
                ? 'Run spatial frequency'
                : 'Run combined analysis (M1 + M2)'}
          </Button>
        </>
      )}
    </Card>
  )
}
