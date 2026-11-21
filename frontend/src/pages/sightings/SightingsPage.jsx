import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SightingsIcon } from '../../components/icons.jsx'
import { useZebra } from '../../components/identify/identifyHelpers.js'
import SightingFormDialog from '../../components/sightings/SightingFormDialog.jsx'
import { SightingRow } from '../../components/sightings/SightingRow.jsx'
import { ZebraPicker } from '../../components/sightings/ZebraPicker.jsx'
import { Button, Card, EmptyState, ErrorState, Input, Select, Skeleton } from '../../components/ui/index.js'
import { useDebounced, useResource } from '../../hooks/useResource.js'
import { formatCount } from '../../lib/format.js'
import { sightingsApi } from '../../services/zebraid.js'

const PAGE_SIZE = 20

/** yyyy-mm-dd (local) -> ISO at local midnight; `nextDay` for exclusive upper bounds. */
function dayToIso(day, nextDay = false) {
  if (!day) return undefined
  const [y, m, d] = day.split('-').map(Number)
  return new Date(y, m - 1, d + (nextDay ? 1 : 0)).toISOString()
}

/** Filters live in the URL: ?q=&zebra=&identity=unidentified&from=&to=&page= */
export default function SightingsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const zebraId = params.get('zebra') || ''
  const identity = params.get('identity') || ''
  const from = params.get('from') || ''
  const to = params.get('to') || ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const recordOpen = params.get('record') === '1'

  const update = useCallback(
    (changes, { resetPage = true } = {}) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(changes)) {
            if (v === '' || v == null) next.delete(k)
            else next.set(k, String(v))
          }
          if (resetPage) next.delete('page')
          return next
        },
        { replace: true },
      ),
    [setParams],
  )

  const [text, setText] = useState(q)
  const debounced = useDebounced(text.trim())
  const pushed = useRef(debounced)
  useEffect(() => {
    if (debounced === pushed.current) return
    pushed.current = debounced
    update({ q: debounced })
  }, [debounced, update])

  const zebra = useZebra(zebraId || null)
  const rangeError = from && to && to < from ? '“To” is before “From”' : null

  const query = {
    location_name: q || undefined,
    zebra_id: identity === 'unidentified' ? undefined : zebraId || undefined,
    unidentified_only: identity === 'unidentified' || undefined,
    since: dayToIso(from),
    until: dayToIso(to, true),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  }
  const list = useResource(rangeError ? null : ['sightings', query], () => sightingsApi.list(query))
  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filtered = Boolean(q || zebraId || identity || from || to)

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Field records</div>
          <h2 className="mt-1 text-xl font-semibold text-ink">Sightings</h2>
          <p className="mt-1 text-sm text-muted">
            {list.data ? `${formatCount(total)} ${filtered ? 'matching' : 'recorded'} sighting${total === 1 ? '' : 's'}` : 'Field observations by place and time'}
          </p>
        </div>
        <Button onClick={() => update({ record: 1 }, { resetPage: false })} leftIcon={<span aria-hidden="true">+</span>}>
          Record sighting
        </Button>
      </div>

      <Card className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-[1.4fr_1.2fr_0.9fr_0.8fr_0.8fr]">
        <Input label="Location" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search place names" maxLength={200} />
        {identity === 'unidentified' ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">Zebra</span>
            <div className="flex h-10 items-center rounded-control border border-line bg-raised/50 px-3 text-sm text-faint">Unidentified only</div>
          </div>
        ) : (
          <ZebraPicker
            label="Zebra"
            emptyLabel="Any zebra"
            value={zebraId ? (zebra.data ?? { id: zebraId, code: '…' }) : null}
            onChange={(z) => update({ zebra: z?.id ?? '' })}
          />
        )}
        <Select label="Identity" value={identity} onChange={(e) => update({ identity: e.target.value, zebra: e.target.value ? '' : zebraId })}>
          <option value="">All sightings</option>
          <option value="unidentified">Unidentified only</option>
        </Select>
        <Input label="From" type="date" value={from} max={to || undefined} onChange={(e) => update({ from: e.target.value })} />
        <Input label="To" type="date" value={to} min={from || undefined} onChange={(e) => update({ to: e.target.value })} error={rangeError} />
      </Card>

      <Card>
        {rangeError ? (
          <EmptyState title="Invalid date range" description="Choose a “To” date on or after the “From” date." />
        ) : list.error ? (
          <ErrorState title="Could not load sightings" error={list.error} onRetry={list.refetch} />
        ) : !list.data ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : list.data.items.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No sightings match these filters"
              description="Try a different place, zebra or date range."
              action={
                <Button variant="secondary" onClick={() => (setText(''), update({ q: '', zebra: '', identity: '', from: '', to: '' }))}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<SightingsIcon />}
              title="No sightings recorded yet"
              description="Record where and when an animal was observed. Link it to a registered zebra when the identity is known."
              action={<Button onClick={() => update({ record: 1 }, { resetPage: false })}>Record sighting</Button>}
            />
          )
        ) : (
          <>
            <ul className={`divide-y divide-line ${list.loading ? 'opacity-60' : ''}`}>
              {list.data.items.map((s) => (
                <SightingRow key={s.id} sighting={s} />
              ))}
            </ul>
            {pages > 1 && (
              <nav aria-label="Pagination" className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-muted">
                <span className="tabular">
                  Page {page} of {pages}
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => update({ page: page - 1 }, { resetPage: false })}>
                    Previous
                  </Button>
                  <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => update({ page: page + 1 }, { resetPage: false })}>
                    Next
                  </Button>
                </div>
              </nav>
            )}
          </>
        )}
      </Card>

      {recordOpen && (
        <SightingFormDialog
          onClose={() => update({ record: '' }, { resetPage: false })}
          onSaved={(s) => navigate(`/sightings/${s.id}`)}
        />
      )}
    </div>
  )
}
