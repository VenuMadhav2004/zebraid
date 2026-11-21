import { useId, useState } from 'react'
import { cn } from '../../lib/cn.js'
import { formatBytes } from '../../lib/format.js'
import { ALLOWED_IMAGE_TYPES, checkImageFile } from '../../services/zebraid.js'
import { AlertIcon, CloseIcon, IdentifyIcon, RefreshIcon } from '../icons.jsx'
import { Button, Card, Input, Spinner } from '../ui/index.js'

export function MlStatus({ capability, onRetry }) {
  if (!capability) {
    return (
      <div className="flex items-center gap-2 rounded-control border border-line bg-raised px-3 py-2.5 text-xs text-muted">
        <Spinner className="h-3.5 w-3.5" /> Checking identification service…
      </div>
    )
  }
  if (capability.available) {
    const state = capability.model_state
    const detail =
      state === 'loaded'
        ? `Model loaded${capability.model_load_seconds != null ? ` (${capability.model_load_seconds} s)` : ''}`
        : state === 'loading'
          ? 'Loading model weights in the background (about 1–2 min)…'
          : state === 'failed'
            ? 'Last model load failed; it will be retried on the next request'
            : 'Model loads on the first identification (about 1–2 min)'
    return (
      <div className="rounded-control border border-success/30 bg-success/10 px-3 py-2.5 text-xs">
        <div className="flex items-center gap-2 text-success">
          <span className="h-1.5 w-1.5 rounded-full bg-success" /> Identification service available
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-muted">
          {state === 'loading' && <Spinner className="h-3 w-3" />}
          <span>{detail}</span>
        </div>
        {capability.model_name && (
          <div className="mt-1 font-mono text-[0.625rem] text-faint">
            {capability.model_name} @ {String(capability.model_revision || '').slice(0, 7)} · {capability.device || 'cpu'}
          </div>
        )}
      </div>
    )
  }
  return (
    <div role="status" className="rounded-control border border-warning/35 bg-warning/10 p-3 text-xs">
      <div className="flex items-center gap-2 font-medium text-warning">
        <AlertIcon className="h-4 w-4" /> ML service unavailable
      </div>
      <p className="mt-1.5 leading-relaxed text-muted">{capability.reason}</p>
      <button type="button" onClick={onRetry} className="mt-2 inline-flex items-center gap-1.5 text-muted hover:text-ink">
        <RefreshIcon className="h-3.5 w-3.5" /> Check again
      </button>
    </div>
  )
}

/**
 * Query photograph intake: drag/drop or browse, client-side validation, metadata.
 * The preview itself is shown in the centre viewer.
 */
export function UploadPanel({ file, meta, onFile, capturedAt, onCapturedAt, capability, onRetryCapability, submit, onSubmit }) {
  const inputId = useId()
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const busy = submit.state === 'uploading' || submit.state === 'identifying'

  function accept(f) {
    const problem = checkImageFile(f)
    setError(problem)
    onFile(problem ? null : f)
  }

  const unavailable = capability && !capability.available

  return (
    <Card className="flex flex-col gap-4 p-4">
      <div>
        <div className="eyebrow">Query</div>
        <h2 className="mt-1 text-[0.9375rem] font-semibold text-ink">Field photograph</h2>
      </div>

      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault()
          if (!busy) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (!busy && e.dataTransfer.files?.[0]) accept(e.dataTransfer.files[0])
        }}
        className={cn(
          'stripe-texture flex cursor-pointer flex-col items-center justify-center gap-2 rounded-control border border-dashed px-4 py-8 text-center transition-colors',
          dragging ? 'border-accent bg-accent/5' : 'border-line-strong hover:border-accent/60',
          error && 'border-danger/60',
          busy && 'pointer-events-none opacity-50',
        )}
      >
        <IdentifyIcon className="h-7 w-7 text-accent" />
        <span className="text-sm text-ink">{file ? 'Replace photograph' : 'Drop a photograph or click to browse'}</span>
        <span className="text-xs text-faint">JPEG, PNG or WebP · up to 10 MB</span>
      </label>
      <input
        id={inputId}
        type="file"
        accept={ALLOWED_IMAGE_TYPES.join(',')}
        className="sr-only"
        disabled={busy}
        onChange={(e) => {
          if (e.target.files?.[0]) accept(e.target.files[0])
          e.target.value = ''
        }}
      />
      {error && (
        <p role="alert" className="-mt-2 text-xs text-danger">
          {error}
        </p>
      )}

      {file && (
        <div className="rounded-control border border-line bg-raised/60 p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm text-ink">{file.name}</div>
              <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <dt className="text-faint">Format</dt>
                <dd className="text-muted">{file.type.replace('image/', '').toUpperCase()}</dd>
                <dt className="text-faint">Size</dt>
                <dd className="text-muted">{formatBytes(file.size)}</dd>
                <dt className="text-faint">Dimensions</dt>
                <dd className="tabular text-muted">{meta?.width ? `${meta.width} × ${meta.height}` : meta?.error ? 'Unreadable' : '…'}</dd>
              </dl>
            </div>
            <Button variant="ghost" size="icon" aria-label="Clear photograph" disabled={busy} onClick={() => (onFile(null), setError(null))}>
              <CloseIcon className="h-4 w-4" />
            </Button>
          </div>
          {meta?.error && <p className="mt-2 text-xs text-danger">{meta.error}</p>}
        </div>
      )}

      <Input
        label="Captured at"
        type="datetime-local"
        value={capturedAt}
        onChange={(e) => onCapturedAt(e.target.value)}
        hint="Optional: when the photograph was taken"
        disabled={busy}
      />

      <MlStatus capability={capability} onRetry={onRetryCapability} />

      {submit.state === 'uploading' && (
        <div className="space-y-1.5" aria-live="polite">
          <div className="flex justify-between text-xs text-muted">
            <span>Uploading</span>
            <span className="tabular">{submit.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-raised">
            <div className="h-full bg-accent transition-[width]" style={{ width: `${submit.progress}%` }} />
          </div>
        </div>
      )}
      {submit.state === 'error' && (
        <p role="alert" className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {submit.error}
        </p>
      )}

      <Button
        size="lg"
        onClick={onSubmit}
        loading={busy}
        disabled={!file || Boolean(meta?.error) || !capability || unavailable}
        leftIcon={<IdentifyIcon className="h-4 w-4" />}
      >
        {unavailable ? 'Model unavailable' : submit.state === 'identifying' ? 'Identifying…' : 'Identify zebra'}
      </Button>
      <p className="text-[0.6875rem] leading-relaxed text-faint">
        Results are ranked suggestions with similarity scores, not identities. A researcher confirms every identification.
      </p>
    </Card>
  )
}
