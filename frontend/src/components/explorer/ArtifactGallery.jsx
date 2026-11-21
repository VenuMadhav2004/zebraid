import { useEffect, useState } from 'react'
import { cn } from '../../lib/cn.js'
import { getArtifactUrl } from '../../services/stripeAnalysis.js'
import { Badge, Card, Dialog, Spinner } from '../ui/index.js'

const LABELS = {
  mask: 'Stripe mask',
  orientation: 'Orientation map',
  width: 'Width map',
  overlay: 'Segmentation overlay',
  original_roi: 'Original ROI',
  filtered: 'Filtered ROI',
  intensity_mask: 'Intensity mask',
  spectrum: '2D FFT spectrum',
}

function ArtifactThumb({ jobId, name, active, onSelect }) {
  const [state, setState] = useState({ url: null, loading: true, error: false, retried: false })

  useEffect(() => {
    let alive = true
    setState({ url: null, loading: true, error: false, retried: false })
    getArtifactUrl(jobId, name, 600)
      .then(({ url }) => alive && setState({ url, loading: false, error: false, retried: false }))
      .catch(() => alive && setState({ url: null, loading: false, error: true, retried: false }))
    return () => {
      alive = false
    }
  }, [jobId, name])

  function handleImgError() {
    if (state.retried) {
      setState((s) => ({ ...s, error: true }))
      return
    }
    getArtifactUrl(jobId, name, 600)
      .then(({ url }) => setState({ url, loading: false, error: false, retried: true }))
      .catch(() => setState((s) => ({ ...s, error: true, retried: true })))
  }

  const label = LABELS[name] || name
  return (
    <button
      type="button"
      onClick={() => state.url && onSelect({ name, label, url: state.url })}
      className={cn(
        'group overflow-hidden rounded-control border text-left transition-colors',
        active ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-line-strong',
      )}
    >
      <div className="relative aspect-[4/3] bg-canvas flex items-center justify-center">
        {state.loading ? (
          <Spinner className="h-4 w-4 text-accent" />
        ) : state.error || !state.url ? (
          <span className="text-[0.6875rem] text-faint">Image unavailable</span>
        ) : (
          <img src={state.url} alt={label} onError={handleImgError} className="h-full w-full object-contain" />
        )}
      </div>
      <div className="flex items-center justify-between gap-1 bg-raised px-2 py-1.5 text-[0.6875rem]">
        <span className="truncate text-ink">{label}</span>
        {active && <span className="text-accent">On</span>}
      </div>
    </button>
  )
}

export default function ArtifactGallery({ job, activeOverlay, opacity, onOpacityChange, onToggleOverlay }) {
  const [spectrumModal, setSpectrumModal] = useState(null)
  const names = job?.artifacts ?? []
  if (!job || names.length === 0) return null

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Visualization artifacts</h3>
        <Badge tone="neutral">{names.length} PNG{names.length === 1 ? '' : 's'}</Badge>
      </div>

      {activeOverlay && (
        <div className="rounded-control border border-line bg-raised/60 px-3 py-2 space-y-1.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-ink">Overlay: {activeOverlay.label}</span>
            <button type="button" onClick={() => onToggleOverlay(null)} className="text-muted hover:text-ink underline">
              Clear
            </button>
          </div>
          <label className="flex items-center gap-2 text-[0.6875rem] text-faint">
            <span>Opacity</span>
            <input
              type="range"
              min="0.1"
              max="1"
              step="0.05"
              value={opacity}
              onChange={(e) => onOpacityChange(Number(e.target.value))}
              className="flex-1 accent-[var(--color-accent)]"
            />
            <span className="tabular font-mono text-ink">{Math.round(opacity * 100)}%</span>
          </label>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        {names.map((name) => (
          <ArtifactThumb
            key={`${job.id}-${name}`}
            jobId={job.id}
            name={name}
            active={activeOverlay?.name === name && activeOverlay?.jobId === job.id}
            onSelect={(item) => {
              if (name === 'spectrum') {
                setSpectrumModal(item)
              } else if (activeOverlay?.name === name && activeOverlay?.jobId === job.id) {
                onToggleOverlay(null)
              } else {
                const bounds = job.kind === 'spatial_frequency' ? job.roi : null
                onToggleOverlay({ ...item, jobId: job.id, bounds })
              }
            }}
          />
        ))}
      </div>
      <p className="text-[0.6875rem] text-faint">
        Click spatial maps to overlay in the viewport; click 2D FFT spectrum to inspect full-size.
      </p>

      {spectrumModal && (
        <Dialog open size="lg" title="2D FFT Power Spectrum" description="Frequency-domain log-magnitude plot (non-spatial)." onClose={() => setSpectrumModal(null)}>
          <div className="rounded-control bg-canvas p-2 flex justify-center">
            <img src={spectrumModal.url} alt="2D FFT spectrum" className="max-h-[65vh] object-contain" />
          </div>
        </Dialog>
      )}
    </Card>
  )
}
