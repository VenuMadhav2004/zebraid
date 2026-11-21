import { useState } from 'react'

function formatValue(v) {
  if (v === null || v === undefined) return <span className="text-faint">null</span>
  if (typeof v === 'number') return <span className="tabular">{Number.isInteger(v) ? v : v.toFixed(4)}</span>
  if (typeof v === 'boolean') return String(v)
  if (typeof v === 'string') return v
  return (
    <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[0.6875rem] text-muted">
      {JSON.stringify(v, null, 2)}
    </pre>
  )
}

const humanize = (key) => key.replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

/**
 * Renders evidence exactly as stored by the ML layer. Keys and values are shown
 * verbatim (no interpretation, thresholds or derived numbers).
 */
export function EvidenceTable({ evidence, emptyText = 'The model supplied no evidence for this candidate.' }) {
  const [raw, setRaw] = useState(false)
  const entries = Object.entries(evidence || {})
  if (entries.length === 0) return <p className="text-sm text-faint">{emptyText}</p>
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button type="button" onClick={() => setRaw((r) => !r)} className="text-xs text-muted hover:text-accent">
          {raw ? 'Table view' : 'Raw JSON'}
        </button>
      </div>
      {raw ? (
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-control bg-raised p-3 font-mono text-[0.6875rem] text-muted">
          {JSON.stringify(evidence, null, 2)}
        </pre>
      ) : (
        <dl className="divide-y divide-line rounded-control border border-line">
          {entries.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[minmax(0,10rem)_1fr] gap-3 px-3 py-2 text-xs">
              <dt className="truncate text-muted" title={k}>
                {humanize(k)}
              </dt>
              <dd className="min-w-0 break-words text-ink">{formatValue(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
