import { Link } from 'react-router-dom'
import { formatBytes, formatDateTime } from '../../lib/format.js'
import { Badge, Button, Card, Input } from '../ui/index.js'

function Panel({ title, badge, children }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {badge}
      </div>
      {children}
    </Card>
  )
}

function Rows({ rows }) {
  return (
    <dl className="divide-y divide-line text-xs">
      {rows
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => (
          <div key={k} className="grid grid-cols-[7.5rem_1fr] gap-2 py-1.5">
            <dt className="text-faint">{k}</dt>
            <dd className="min-w-0 break-all text-ink">{v ?? <span className="text-faint">Not recorded</span>}</dd>
          </div>
        ))}
    </dl>
  )
}

/** Facts about the file / stored record only. */
export function ImageInfoPanel({ source, naturalSize }) {
  if (!source) return null
  const rec = source.record
  const rows = [
    ['Source', source.type === 'local' ? 'Local file (not uploaded)' : 'Image library'],
    ['Name', source.type === 'local' ? source.file.name : undefined],
    ['Image ID', rec ? <span className="font-mono">{rec.id}</span> : undefined],
    ['Kind', rec?.kind],
    ['Format', (rec?.content_type || source.file?.type || '').replace('image/', '').toUpperCase() || null],
    ['File size', formatBytes(rec?.size_bytes ?? source.file?.size)],
    ['Dimensions', naturalSize ? <span className="tabular">{naturalSize.width} × {naturalSize.height} px</span> : null],
    ['SHA-256', rec ? (rec.sha256 ? <span className="font-mono">{rec.sha256.slice(0, 16)}…</span> : null) : undefined],
    ['Captured', rec ? (rec.captured_at ? formatDateTime(rec.captured_at) : null) : undefined],
    ['Uploaded by', rec ? rec.uploaded_by : undefined],
    ['Stored', rec ? formatDateTime(rec.created_at) : undefined],
    [
      'Crop of',
      rec?.source_image_id ? (
        <Link to={`/stripes?image=${rec.source_image_id}`} className="font-mono text-accent hover:underline">
          {rec.source_image_id.slice(0, 8)}
        </Link>
      ) : undefined,
    ],
    [
      'Crop box',
      rec?.crop_bbox ? <span className="tabular font-mono">{`x ${rec.crop_bbox.x}, y ${rec.crop_bbox.y}, ${rec.crop_bbox.width} × ${rec.crop_bbox.height}`}</span> : undefined,
    ],
  ]
  return (
    <Panel title="Image metadata" badge={<Badge tone="success">Recorded</Badge>}>
      <Rows rows={rows} />
    </Panel>
  )
}

const fmt = (n, d = 1) => (Number.isFinite(n) ? n.toFixed(d) : '—')

/**
 * Geometry of the view and the selected region, computed in the browser from pixel
 * coordinates only. Nothing here describes stripes.
 */
export function SpatialPanel({ naturalSize, view, cursor, roi, onRoiChange, cropAction }) {
  const area = roi ? roi.width * roi.height : null
  const share = roi && naturalSize ? (100 * area) / (naturalSize.width * naturalSize.height) : null

  function edit(field, value) {
    const n = Math.round(Number(value))
    if (!naturalSize || !Number.isFinite(n)) return
    const next = { ...(roi || { x: 0, y: 0, width: Math.min(256, naturalSize.width), height: Math.min(256, naturalSize.height) }), [field]: n }
    next.x = Math.max(0, Math.min(next.x, naturalSize.width - 2))
    next.y = Math.max(0, Math.min(next.y, naturalSize.height - 2))
    next.width = Math.max(2, Math.min(next.width, naturalSize.width - next.x))
    next.height = Math.max(2, Math.min(next.height, naturalSize.height - next.y))
    onRoiChange(next)
  }

  return (
    <Panel title="Spatial information" badge={<Badge tone="info">Computed geometry</Badge>}>
      <Rows
        rows={[
          ['Zoom', view ? <span className="tabular">{fmt(view.scale * 100, 0)}%</span> : null],
          ['Cursor', cursor ? <span className="tabular font-mono">x {cursor.x}, y {cursor.y}</span> : <span className="text-faint">Outside image</span>],
        ]}
      />
      <div className="mt-3 border-t border-line pt-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="eyebrow">Region of interest</span>
          {roi && (
            <button type="button" onClick={() => onRoiChange(null)} className="text-xs text-muted hover:text-ink">
              Clear
            </button>
          )}
        </div>
        <div className="grid grid-cols-4 gap-2">
          {['x', 'y', 'width', 'height'].map((f) => (
            <Input
              key={f}
              label={f === 'width' ? 'W' : f === 'height' ? 'H' : f.toUpperCase()}
              type="number"
              inputMode="numeric"
              min={f === 'width' || f === 'height' ? 2 : 0}
              value={roi ? roi[f] : ''}
              placeholder="—"
              disabled={!naturalSize}
              onChange={(e) => edit(f, e.target.value)}
              inputClassName="tabular h-9 px-2 font-mono text-xs"
            />
          ))}
        </div>
        {roi ? (
          <Rows
            rows={[
              ['Area', <span key="a" className="tabular">{area.toLocaleString()} px²</span>],
              ['Share of image', <span key="s" className="tabular">{fmt(share, 2)}%</span>],
              ['Aspect (W:H)', <span key="r" className="tabular">{fmt(roi.width / roi.height, 3)}</span>],
              ['Centre', <span key="c" className="tabular font-mono">x {fmt(roi.x + roi.width / 2)}, y {fmt(roi.y + roi.height / 2)}</span>],
            ]}
          />
        ) : (
          <p className="mt-2 text-xs text-faint">Choose the Region tool and drag on the image, or type values above.</p>
        )}
        {cropAction}
      </div>
    </Panel>
  )
}

/** Shown until real analysis output exists. Never renders placeholder numbers. */
export function AnalysisPanel({ title, capability, result, emptyText }) {
  if (result && Object.keys(result).length) {
    return (
      <Panel title={title} badge={<Badge tone="success">Computed by model</Badge>}>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-control bg-raised p-2.5 font-mono text-[0.6875rem] text-muted">
          {JSON.stringify(result, null, 2)}
        </pre>
      </Panel>
    )
  }
  return (
    <Panel title={title} badge={<Badge tone="warning">Unavailable</Badge>}>
      <div className="stripe-texture rounded-control border border-dashed border-line-strong px-3 py-4 text-xs leading-relaxed text-muted">
        <p>{emptyText}</p>
        {capability && !capability.available && <p className="mt-2 text-faint">{capability.reason}</p>}
      </div>
    </Panel>
  )
}

export function AnalyzeButton({ capability, disabled, onClick }) {
  const unavailable = !capability?.available
  return (
    <div className="space-y-1.5">
      <Button className="w-full" disabled={unavailable || disabled} onClick={onClick}>
        {unavailable ? 'Analysis service unavailable' : 'Analyse region'}
      </Button>
      <p className="text-[0.6875rem] text-faint">
        {unavailable ? 'No stripe measurements are estimated in the browser.' : 'Sends the selected region to the analysis service.'}
      </p>
    </div>
  )
}
