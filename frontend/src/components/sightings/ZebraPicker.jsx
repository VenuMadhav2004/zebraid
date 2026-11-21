import { useId, useState } from 'react'
import { useDebounced, useResource } from '../../hooks/useResource.js'
import { cn } from '../../lib/cn.js'
import { zebrasApi } from '../../services/zebraid.js'
import { CloseIcon } from '../icons.jsx'
import { Spinner } from '../ui/index.js'

/**
 * Search-as-you-type selector for a registered zebra.
 * value: zebra object | null (null = unidentified). Never creates zebras.
 */
export function ZebraPicker({ label = 'Zebra', value, onChange, disabled, hint, emptyLabel = 'Unidentified', error }) {
  const id = useId()
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const q = useDebounced(text.trim(), 250)
  const results = useResource(open ? ['zebra-pick', q] : null, () => zebrasApi.list({ search: q || undefined, limit: 8 }))

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}
      </label>
      {value ? (
        <div className="flex h-10 items-center justify-between gap-2 rounded-control border border-line bg-raised px-3">
          <span className="min-w-0 truncate text-sm">
            <span className="font-mono text-accent">{value.code}</span>
            {value.name && <span className="text-muted"> · {value.name}</span>}
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(null)}
            aria-label={`Clear ${label.toLowerCase()}`}
            className="rounded p-1 text-faint hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div className="relative">
          <input
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-controls={`${id}-list`}
            aria-autocomplete="list"
            autoComplete="off"
            disabled={disabled}
            value={text}
            placeholder={`${emptyLabel} · type a code or name`}
            onChange={(e) => (setText(e.target.value), setOpen(true))}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            className={cn(
              'h-10 w-full rounded-control border bg-raised px-3 text-sm text-ink placeholder:text-faint focus:border-accent/70 focus:outline-none focus:ring-2 focus:ring-accent/20',
              error ? 'border-danger/60' : 'border-line hover:border-line-strong',
            )}
          />
          {open && (
            <ul
              id={`${id}-list`}
              role="listbox"
              className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-control border border-line bg-surface py-1 shadow-pop"
            >
              {results.loading && !results.data ? (
                <li className="flex items-center gap-2 px-3 py-2 text-xs text-muted">
                  <Spinner className="h-3.5 w-3.5" /> Searching…
                </li>
              ) : results.error ? (
                <li className="px-3 py-2 text-xs text-danger">{results.error.message}</li>
              ) : results.data?.items.length ? (
                results.data.items.map((z) => (
                  <li key={z.id} role="option" aria-selected="false">
                    <button
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => (onChange(z), setText(''), setOpen(false))}
                      className="flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm hover:bg-raised"
                    >
                      <span className="font-mono text-accent">{z.code}</span>
                      <span className="truncate text-muted">{z.name || 'Unnamed'}</span>
                      {z.status !== 'active' && <span className="ml-auto text-[0.6875rem] text-faint">{z.status}</span>}
                    </button>
                  </li>
                ))
              ) : (
                <li className="px-3 py-2 text-xs text-faint">No registered zebra matches “{q}”</li>
              )}
            </ul>
          )}
        </div>
      )}
      {error ? <p className="text-xs text-danger">{error}</p> : hint && <p className="text-xs text-faint">{hint}</p>}
    </div>
  )
}
