import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { formatBytes } from '../../lib/format.js'
import { fetchScanFiles, listHideScans } from '../../services/hideScans.js'
import { Badge, Button, Card, Spinner } from '../ui/index.js'

/**
 * One-click loading of authorized scans stored on the server. `?scan=<id>` loads that scan automatically.
 * onLoaded(files: File[], scan) hands the files to the viewer's existing OBJ/MTL/texture pipeline.
 */
export default function ServerScanPicker({ onLoaded }) {
  const [params, setParams] = useSearchParams()
  const [list, setList] = useState({ loading: true, data: null, error: null })
  const [active, setActive] = useState(null) // {id, loaded, total}
  const [error, setError] = useState(null)
  const abortRef = useRef(null)
  const autoDone = useRef(false)

  useEffect(() => {
    let alive = true
    listHideScans()
      .then((data) => alive && setList({ loading: false, data, error: null }))
      .catch((err) => alive && setList({ loading: false, data: null, error: err }))
    return () => {
      alive = false
      abortRef.current?.abort()
    }
  }, [])

  async function load(scan) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setError(null)
    setActive({ id: scan.id, loaded: 0, total: scan.total_bytes })
    try {
      const files = await fetchScanFiles(scan, {
        signal: controller.signal,
        onProgress: (p) => setActive({ id: scan.id, ...p }),
      })
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('scan', scan.id)
        return next
      }, { replace: true })
      onLoaded(files, scan)
    } catch (err) {
      if (err?.name !== 'CanceledError' && err?.name !== 'AbortError') setError(err.message || 'Download failed')
    } finally {
      setActive(null)
    }
  }

  // Auto-load ?scan=<id> once the list is known.
  const wanted = params.get('scan')
  useEffect(() => {
    if (autoDone.current || !wanted || !list.data?.scans?.length) return
    const scan = list.data.scans.find((s) => s.id === wanted)
    if (scan) {
      autoDone.current = true
      load(scan)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, list.data])

  const scans = list.data?.scans ?? []
  const pct = active && active.total ? Math.min(100, Math.round((active.loaded / active.total) * 100)) : 0

  return (
    <Card className="p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs">
          <span className="font-semibold text-ink">Authorized scans on server</span>
          <span className="ml-2 text-faint">Organiser-provided hide scans, streamed to this browser only</span>
        </div>
        {list.loading ? <Spinner className="h-3.5 w-3.5" /> : <Badge tone={scans.length ? 'success' : 'neutral'}>{scans.length} available</Badge>}
      </div>
      {list.error && <p className="text-xs text-danger">{list.error.message}</p>}
      {list.data && !list.data.available && <p className="text-xs text-faint">{list.data.reason}</p>}
      {scans.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {scans.map((s) => (
            <Button
              key={s.id}
              size="sm"
              variant={wanted === s.id ? 'primary' : 'secondary'}
              disabled={Boolean(active)}
              loading={active?.id === s.id}
              onClick={() => load(s)}
              title={s.files.map((f) => `${f.name} (${formatBytes(f.size_bytes)})`).join('\n')}
            >
              {s.label} · {formatBytes(s.total_bytes)}
            </Button>
          ))}
        </div>
      )}
      {active && (
        <div className="space-y-1" aria-live="polite">
          <div className="flex justify-between text-[0.6875rem] text-muted">
            <span>Downloading {active.id}…</span>
            <span className="tabular font-mono">
              {formatBytes(active.loaded)} / {formatBytes(active.total)} ({pct}%)
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-raised">
            <div className="h-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
          </div>
          <button type="button" onClick={() => abortRef.current?.abort()} className="text-[0.6875rem] text-muted underline hover:text-ink">
            Cancel
          </button>
        </div>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
    </Card>
  )
}
