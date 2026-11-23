import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { formatBytes, formatDateTime } from '../../lib/format.js'
import { fetchScanFiles, importHideScans, listHideScans } from '../../services/hideScans.js'
import { Badge, Button, Card, Input, Select, Spinner } from '../ui/index.js'

/**
 * Dataset asset gallery & one-click loading of authorized scans stored on the server.
 * `?scan=<id>` loads that scan automatically.
 * onLoaded(files: File[], scan) hands the files to the viewer's existing OBJ/MTL/texture pipeline.
 */
export default function ServerScanPicker({ onLoaded }) {
  const [params, setParams] = useSearchParams()
  const [list, setList] = useState({ loading: true, data: null, error: null })
  const [active, setActive] = useState(null) // {id, loaded, total}
  const [importing, setImporting] = useState(false)
  const [importSummary, setImportSummary] = useState(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedMeta, setSelectedMeta] = useState(null)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)
  const autoDone = useRef(false)

  const refresh = useCallback(() => {
    setList((prev) => ({ ...prev, loading: true, error: null }))
    return listHideScans()
      .then((data) => setList({ loading: false, data, error: null }))
      .catch((err) => setList({ loading: false, data: null, error: err }))
  }, [])

  useEffect(() => {
    refresh()
    return () => {
      abortRef.current?.abort()
    }
  }, [refresh])

  async function load(scan) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setError(null)
    setSelectedMeta(scan)
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

  async function handleImport() {
    setImporting(true)
    setError(null)
    setImportSummary(null)
    try {
      const res = await importHideScans({})
      setImportSummary(res)
      await refresh()
    } catch (err) {
      setError(err.message || 'Dataset import failed')
    } finally {
      setImporting(false)
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

  const scans = useMemo(() => list.data?.scans ?? [], [list.data])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return scans.filter((s) => {
      if (statusFilter !== 'all' && s.validation_status !== statusFilter) return false
      if (!q) return true
      return s.label.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || (s.model_format || '').toLowerCase().includes(q)
    })
  }, [scans, query, statusFilter])

  const pct = active && active.total ? Math.min(100, Math.round((active.loaded / active.total) * 100)) : 0

  return (
    <Card className="p-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs">
          <span className="font-semibold text-ink">Zebra 3D Dataset Gallery</span>
          <span className="ml-2 text-faint">Authorized scans streamed to this browser only</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {list.loading ? <Spinner className="h-3.5 w-3.5" /> : <Badge tone={scans.length ? 'success' : 'neutral'}>{scans.length} registered</Badge>}
          {list.data?.unsupported_count > 0 && (
            <Badge tone="neutral" title="Non-mesh or Metashape project files excluded from viewer">
              {list.data.unsupported_count} unsupported
            </Badge>
          )}
          <Button size="sm" variant="secondary" disabled={importing || Boolean(active)} loading={importing} onClick={handleImport}>
            {importing ? 'Importing Drive dataset…' : 'Sync Drive dataset'}
          </Button>
          <Button size="sm" variant="ghost" disabled={list.loading || importing} onClick={refresh}>
            Refresh
          </Button>
        </div>
      </div>

      {importSummary && (
        <div className="rounded-control border border-success/30 bg-success/10 px-3 py-2 text-xs text-ink">
          Import finished: {importSummary.imported.length} new, {importSummary.skipped_existing.length} existing,{' '}
          {importSummary.duplicates.length} duplicate(s), {importSummary.failed.length} failed,{' '}
          {importSummary.unsupported_count} unsupported file(s) logged.
        </div>
      )}

      {list.error && <p className="text-xs text-danger">{list.error.message}</p>}
      {list.data && !list.data.available && (
        <p className="rounded-control border border-dashed border-line-strong bg-raised/50 px-3 py-2 text-xs text-faint">
          {list.data.reason}
        </p>
      )}

      {scans.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-[1fr_11rem]">
          <Input
            aria-label="Search 3D models"
            placeholder="Search scans (e.g. Zebra 1, obj)…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            inputClassName="h-8 text-xs"
          />
          <Select aria-label="Filter by validation status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All statuses</option>
            <option value="valid">Valid only</option>
            <option value="missing_mtl">Missing MTL</option>
            <option value="missing_texture">Missing texture</option>
          </Select>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {filtered.map((s) => {
            const isSelected = wanted === s.id || selectedMeta?.id === s.id
            return (
              <button
                key={s.id}
                type="button"
                disabled={Boolean(active)}
                onClick={() => load(s)}
                className={`rounded-control border p-2.5 text-left transition-colors ${
                  isSelected ? 'border-accent bg-raised' : 'border-line bg-surface hover:border-line-strong'
                } disabled:opacity-50`}
                title={s.files.map((f) => `${f.name} (${formatBytes(f.size_bytes)})`).join('\n')}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate text-xs font-semibold text-ink">{s.label}</span>
                  <Badge tone={s.validation_status === 'valid' ? 'success' : 'warning'}>{s.model_format?.toUpperCase() || 'OBJ'}</Badge>
                </div>
                <div className="mt-1 flex items-center justify-between text-[0.6875rem] text-faint">
                  <span>{formatBytes(s.total_bytes)} · {s.files.length} files</span>
                  <span>{s.import_status}</span>
                </div>
                {s.sha256 && (
                  <div className="mt-1 truncate font-mono text-[0.625rem] text-faint">
                    sha256:{s.sha256.slice(0, 12)}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}

      {scans.length > 0 && filtered.length === 0 && (
        <p className="text-xs text-faint">No registered 3D scans match “{query}”.</p>
      )}

      {selectedMeta && (
        <div className="rounded-control border border-line bg-raised/60 px-3 py-2 text-[0.6875rem] text-muted flex flex-wrap items-center justify-between gap-2">
          <span>
            <strong className="text-ink">{selectedMeta.label}</strong> · Source: <span className="font-mono">{selectedMeta.dataset_source}</span>
            {selectedMeta.mtl_file ? ` · MTL: ${selectedMeta.mtl_file}` : ''}
            {selectedMeta.texture_files?.length ? ` · Textures: ${selectedMeta.texture_files.join(', ')}` : ''}
          </span>
          {selectedMeta.registered_at && <span>Registered {formatDateTime(selectedMeta.registered_at)}</span>}
        </div>
      )}

      {active && (
        <div className="space-y-1" aria-live="polite">
          <div className="flex justify-between text-[0.6875rem] text-muted">
            <span>Streaming {active.id}…</span>
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
