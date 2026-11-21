import { formatDateTime } from '../../lib/format.js'
import { cn } from '../../lib/cn.js'
import { Badge, Card } from '../ui/index.js'

const STATUS_TONE = { completed: 'success', failed: 'danger', running: 'info', pending: 'warning' }

export default function AnalysisHistory({ items = [], selectedId, onSelect, onDelete, deletingId }) {
  if (!items.length) return null
  return (
    <Card className="p-4 space-y-2.5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">Analysis history</h3>
        <span className="text-xs text-faint">{items.length} saved</span>
      </div>
      <ul className="space-y-1.5">
        {items.map((job) => {
          const selected = job.id === selectedId
          const commit = (job.provider?.source_commit || '').slice(0, 7)
          return (
            <li
              key={job.id}
              className={cn(
                'rounded-control border p-2 text-xs transition-colors',
                selected ? 'border-accent bg-raised/80' : 'border-line hover:border-line-strong',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <button type="button" onClick={() => onSelect(job)} className="min-w-0 flex-1 text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium text-ink">
                      {job.kind === 'stripe_morphology' ? 'Morphology (M1)' : 'Frequency (M2)'}
                    </span>
                    <Badge tone={STATUS_TONE[job.status] || 'neutral'}>{job.status}</Badge>
                  </div>
                  <div className="mt-0.5 truncate text-[0.6875rem] text-faint">
                    {job.roi ? `${job.roi.width}×${job.roi.height}` : 'Full'} · {commit || 'pinned'} · {formatDateTime(job.created_at)}
                  </div>
                </button>
                <button
                  type="button"
                  disabled={job.status === 'running' || deletingId === job.id}
                  onClick={() => onDelete(job.id)}
                  className="text-[0.6875rem] text-danger hover:underline disabled:opacity-40"
                >
                  Delete
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
