import { formatDateTime } from '../../lib/format.js'
import { Card } from '../ui/index.js'
import { RunStatusBadge } from './shared.jsx'

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 py-2 text-xs">
      <dt className="text-faint">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{children ?? <span className="text-faint">—</span>}</dd>
    </div>
  )
}

const UNKNOWN_TEXT = {
  true: 'Model predicted an unknown individual',
  false: 'Model did not predict unknown',
  null: 'No validated unknown threshold applied',
}

export function RunSummary({ run, actions }) {
  const meta = Object.keys(run.processing_metadata || {}).length ? run.processing_metadata : null
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="eyebrow">Identification run</div>
          <h2 className="mt-1 font-mono text-xs text-muted">{run.id.slice(0, 8)}</h2>
        </div>
        <RunStatusBadge status={run.status} />
      </div>
      <dl className="mt-3 divide-y divide-line">
        <Row label="Model">{run.model_name}</Row>
        <Row label="Version">{run.model_version && <span className="font-mono">{run.model_version}</span>}</Row>
        <Row label="Requested">{formatDateTime(run.created_at)}</Row>
        <Row label="Completed">{run.completed_at && formatDateTime(run.completed_at)}</Row>
        <Row label="Requested by">{run.requested_by}</Row>
        <Row label="Unknown">{UNKNOWN_TEXT[String(run.predicted_unknown)]}</Row>
      </dl>
      {run.status === 'failed' && (
        <div role="alert" className="mt-3 rounded-control border border-danger/30 bg-danger/10 p-3 text-xs">
          <div className="font-medium text-danger">Run failed{run.error_code ? ` · ${run.error_code}` : ''}</div>
          <p className="mt-1 text-muted">{run.error_message}</p>
        </div>
      )}
      {meta && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted hover:text-ink">Processing metadata</summary>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-control bg-raised p-2.5 font-mono text-[0.6875rem] text-muted">
            {JSON.stringify(meta, null, 2)}
          </pre>
        </details>
      )}
      {actions && <div className="mt-4 flex flex-col gap-2">{actions}</div>}
    </Card>
  )
}
