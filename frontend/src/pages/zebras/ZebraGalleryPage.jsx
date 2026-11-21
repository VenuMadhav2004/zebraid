import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRightIcon, GalleryIcon } from '../../components/icons.jsx'
import { Button, Card, EmptyState, ErrorState, Input, Select } from '../../components/ui/index.js'
import RegisterZebraDialog from '../../components/zebras/RegisterZebraDialog.jsx'
import { ZebraCard, ZebraCardSkeleton } from '../../components/zebras/ZebraCard.jsx'
import { useDebounced, useResource } from '../../hooks/useResource.js'
import { formatCount } from '../../lib/format.js'
import { ZEBRA_STATUSES, zebrasApi } from '../../services/zebraid.js'

const PAGE_SIZE = 24

/** Filters live in the URL (?q=&status=&species=&sort=&page=) so views are shareable. */
export default function ZebraGalleryPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const status = params.get('status') || ''
  const species = params.get('species') || ''
  const sort = params.get('sort') === '-created_at' ? '-created_at' : 'code'
  const page = Math.max(1, Number(params.get('page')) || 1)
  const registerOpen = params.get('register') === '1'

  const [searchText, setSearchText] = useState(q)
  const [speciesText, setSpeciesText] = useState(species)
  const debouncedSearch = useDebounced(searchText.trim())
  const debouncedSpecies = useDebounced(speciesText.trim())

  const update = useCallback(
    (changes, { resetPage = true } = {}) => {
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
      )
    },
    [setParams],
  )

  // Push debounced text into the URL only when the typed value itself changes
  // (so "Clear filters" or back-navigation is not overwritten by stale text).
  const pushed = useRef({ q: debouncedSearch, species: debouncedSpecies })
  useEffect(() => {
    if (debouncedSearch === pushed.current.q) return
    pushed.current.q = debouncedSearch
    update({ q: debouncedSearch })
  }, [debouncedSearch, update])
  useEffect(() => {
    if (debouncedSpecies === pushed.current.species) return
    pushed.current.species = debouncedSpecies
    update({ species: debouncedSpecies })
  }, [debouncedSpecies, update])

  const query = { search: q, status, species, sort, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
  const list = useResource(['zebras', query], () => zebrasApi.list(query))
  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filtered = Boolean(q || status || species)

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="eyebrow">Registry</div>
          <h2 className="mt-1 text-xl font-semibold text-ink">Zebra gallery</h2>
          <p className="mt-1 text-sm text-muted">
            {list.data ? `${formatCount(total)} ${filtered ? 'matching' : 'registered'} ${total === 1 ? 'individual' : 'individuals'}` : 'Registered individuals and their reference photographs'}
          </p>
        </div>
        <Button onClick={() => update({ register: 1 }, { resetPage: false })} leftIcon={<span aria-hidden="true" className="text-base leading-none">+</span>}>
          Register zebra
        </Button>
      </div>

      <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]">
        <Input
          label="Search"
          type="search"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="Code or name"
          maxLength={120}
        />
        <Select label="Status" value={status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">All statuses</option>
          {ZEBRA_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s[0].toUpperCase() + s.slice(1)}
            </option>
          ))}
        </Select>
        <Input
          label="Species"
          value={speciesText}
          onChange={(e) => setSpeciesText(e.target.value)}
          placeholder="Exact, e.g. Equus quagga"
          maxLength={80}
        />
        <Select label="Sort" value={sort} onChange={(e) => update({ sort: e.target.value === 'code' ? '' : e.target.value })}>
          <option value="code">Code A–Z</option>
          <option value="-created_at">Newest first</option>
        </Select>
      </Card>

      {list.error ? (
        <Card>
          <ErrorState title="Could not load zebras" error={list.error} onRetry={list.refetch} />
        </Card>
      ) : list.loading && !list.data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <ZebraCardSkeleton key={i} />
          ))}
        </div>
      ) : list.data.items.length === 0 ? (
        <Card>
          {filtered ? (
            <EmptyState
              title="No zebras match these filters"
              description="Try a different code, name or species, or clear the filters."
              action={
                <Button variant="secondary" onClick={() => (setSearchText(''), setSpeciesText(''), update({ q: '', status: '', species: '' }))}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<GalleryIcon />}
              title="No zebras registered yet"
              description="Register the first individual with a clear flank photograph to start the reference gallery."
              action={<Button onClick={() => update({ register: 1 }, { resetPage: false })}>Register zebra</Button>}
            />
          )}
        </Card>
      ) : (
        <>
          <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 ${list.loading ? 'opacity-60' : ''}`}>
            {list.data.items.map((z) => (
              <ZebraCard key={z.id} zebra={z} />
            ))}
          </div>
          {pages > 1 && (
            <nav aria-label="Pagination" className="flex items-center justify-between text-sm text-muted">
              <span className="tabular">
                Page {page} of {pages}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => update({ page: page - 1 }, { resetPage: false })}>
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= pages}
                  rightIcon={<ArrowRightIcon className="h-4 w-4" />}
                  onClick={() => update({ page: page + 1 }, { resetPage: false })}
                >
                  Next
                </Button>
              </div>
            </nav>
          )}
        </>
      )}

      {registerOpen && <RegisterZebraDialog onClose={() => update({ register: '' }, { resetPage: false })} />}
    </div>
  )
}
