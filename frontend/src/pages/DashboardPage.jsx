import { Link, useNavigate } from 'react-router-dom'
import StatCard from '../components/StatCard.jsx'
import { ArrowRightIcon, GalleryIcon, IdentifyIcon, SightingsIcon, StripesIcon } from '../components/icons.jsx'
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Skeleton } from '../components/ui/index.js'
import { ZebraStatusBadge } from '../components/zebras/ZebraBits.jsx'
import { useResource } from '../hooks/useResource.js'
import { formatCount, formatDateTime, timeAgo } from '../lib/format.js'
import { API_BASE_URL } from '../services/api.js'
import { identificationsApi, imagesApi, sightingsApi, zebrasApi } from '../services/zebraid.js'
import { useSystemStatus } from '../services/useSystemStatus.js'

const TONE = { ok: 'success', error: 'danger', loading: 'neutral' }
const RUN_TONE = { completed: 'success', failed: 'danger', running: 'info', pending: 'warning' }
const RECENT = 5

function StatusRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-right text-sm text-ink">{children}</dd>
    </div>
  )
}

/** Count from a list endpoint's `total` (one row fetched). */
function useTotal(key, fetch) {
  const r = useResource(key, () => fetch({ limit: 1 }))
  return { value: r.data ? formatCount(r.data.total) : r.error ? '!' : null, error: r.error }
}

function Stat({ label, total, hint, icon }) {
  return (
    <StatCard
      label={label}
      icon={icon}
      value={total.value ?? <Skeleton className="mt-1 h-8 w-16" />}
      hint={total.error ? `Unavailable: ${total.error.message}` : hint}
    />
  )
}

function RowsSkeleton() {
  return (
    <div className="space-y-3 px-5 pb-5">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-10" />
      ))}
    </div>
  )
}

function Section({ title, eyebrow, to, resource, empty, children }) {
  return (
    <Card className="flex flex-col">
      <CardHeader
        eyebrow={eyebrow}
        title={title}
        action={
          to && (
            <Link to={to} className="inline-flex items-center gap-1 text-xs text-muted hover:text-accent">
              View all <ArrowRightIcon className="h-3.5 w-3.5" />
            </Link>
          )
        }
      />
      {resource.error ? (
        <ErrorState className="py-8" title="Could not load" error={resource.error} onRetry={resource.refetch} />
      ) : !resource.data ? (
        <div className="pt-4">
          <RowsSkeleton />
        </div>
      ) : resource.data.items.length === 0 ? (
        <EmptyState className="py-8" title={empty.title} description={empty.description} />
      ) : (
        <ul className="mt-3 divide-y divide-line border-t border-line">{children(resource.data.items)}</ul>
      )}
    </Card>
  )
}

function Row({ to, primary, secondary, right }) {
  const body = (
    <div className="flex items-center justify-between gap-3 px-5 py-3">
      <div className="min-w-0">
        <div className="truncate text-sm text-ink">{primary}</div>
        <div className="truncate text-xs text-faint">{secondary}</div>
      </div>
      <div className="shrink-0">{right}</div>
    </div>
  )
  return <li>{to ? <Link to={to} className="block transition-colors hover:bg-raised/50">{body}</Link> : body}</li>
}

function ActivityFeed({ zebras, sightings, runs, images }) {
  const sources = [zebras, sightings, runs, images]
  if (sources.some((s) => !s.data && !s.error)) return <RowsSkeleton />
  const events = [
    ...(zebras.data?.items ?? []).map((z) => ({
      at: z.created_at,
      kind: 'Zebra registered',
      text: `${z.code}${z.name ? ` · ${z.name}` : ''}`,
      to: `/zebras/${z.id}`,
      tone: 'accent',
    })),
    ...(sightings.data?.items ?? []).map((s) => ({
      at: s.created_at,
      kind: 'Sighting recorded',
      text: s.location_name || (s.zebra_id ? 'Identified individual' : 'Unidentified individual'),
      tone: 'info',
    })),
    ...(runs.data?.items ?? []).map((r) => ({
      at: r.created_at,
      kind: 'Identification run',
      text: `${r.model_name} · ${r.status}`,
      tone: RUN_TONE[r.status] || 'neutral',
    })),
    ...(images.data?.items ?? []).map((i) => ({
      at: i.created_at,
      kind: 'Photograph uploaded',
      text: `${i.kind} image · ${i.width ?? '?'}×${i.height ?? '?'}`,
      tone: 'neutral',
    })),
  ]
    .sort((a, b) => new Date(b.at) - new Date(a.at))
    .slice(0, 8)

  if (events.length === 0) {
    return <EmptyState className="py-10" title="No activity recorded yet" description="Registrations, uploads, sightings and identification runs will appear here." />
  }
  return (
    <ol className="relative ml-5 mr-5 mb-5 mt-4 border-l border-line">
      {events.map((e, i) => {
        const content = (
          <>
            <div className="flex items-center gap-2">
              <Badge tone={e.tone}>{e.kind}</Badge>
              <time dateTime={e.at} title={formatDateTime(e.at)} className="text-[0.6875rem] text-faint">
                {timeAgo(e.at)}
              </time>
            </div>
            <div className="mt-1 truncate text-sm text-ink">{e.text}</div>
          </>
        )
        return (
          <li key={`${e.kind}-${e.at}-${i}`} className="relative pb-4 pl-5 last:pb-0">
            <span aria-hidden="true" className="absolute -left-[4.5px] top-2 h-2 w-2 rounded-full bg-line-strong ring-4 ring-surface" />
            {e.to ? (
              <Link to={e.to} className="block rounded-control hover:opacity-90">
                {content}
              </Link>
            ) : (
              content
            )}
          </li>
        )
      })}
    </ol>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { api, db } = useSystemStatus()

  const zebraTotal = useTotal(['dash-zebra-total'], zebrasApi.list)
  const imageTotal = useTotal(['dash-image-total'], imagesApi.list)
  const sightingTotal = useTotal(['dash-sighting-total'], sightingsApi.list)
  const referenceTotal = useResource(['dash-ref-total'], () => imagesApi.list({ kind: 'reference', limit: 1 }))

  const recentZebras = useResource(['dash-zebras'], () => zebrasApi.list({ sort: '-created_at', limit: RECENT }))
  const recentSightings = useResource(['dash-sightings'], () => sightingsApi.list({ limit: RECENT }))
  const recentRuns = useResource(['dash-runs'], () => identificationsApi.list({ limit: RECENT }))
  const recentImages = useResource(['dash-images'], () => imagesApi.list({ limit: RECENT }))

  return (
    <div className="space-y-6">
      <section className="stripe-texture relative overflow-hidden rounded-card border border-line bg-surface px-6 py-7 shadow-card sm:px-8">
        <div className="flex flex-col gap-6">
          <div>
            <div className="eyebrow text-accent/80">Field research platform</div>
            <h2 className="mt-2 max-w-2xl text-2xl font-semibold text-ink sm:text-3xl">
              Individual zebra identification from stripe patterns
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
              Register individuals, record sightings and review ranked identity suggestions. Every suggestion is
              verified by a researcher before it becomes an identity.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => navigate('/zebras?register=1')}>Register zebra</Button>
            <Button variant="secondary" leftIcon={<IdentifyIcon className="h-4 w-4" />} onClick={() => navigate('/identify')}>
              Identify
            </Button>
            <Button variant="secondary" leftIcon={<SightingsIcon className="h-4 w-4" />} onClick={() => navigate('/sightings')}>
              Sightings
            </Button>
            <Button variant="ghost" leftIcon={<GalleryIcon className="h-4 w-4" />} onClick={() => navigate('/zebras')}>
              Gallery
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Registered zebras" total={zebraTotal} hint="Known individuals" icon={GalleryIcon} />
        <Stat
          label="Photographs"
          total={imageTotal}
          hint={
            referenceTotal.data
              ? `${formatCount(referenceTotal.data.total)} reference image${referenceTotal.data.total === 1 ? '' : 's'}`
              : 'All uploaded images'
          }
          icon={StripesIcon}
        />
        <Stat label="Sightings" total={sightingTotal} hint="Field observations" icon={SightingsIcon} />
        <StatCard
          label="Identification runs"
          icon={IdentifyIcon}
          value={recentRuns.data ? formatCount(recentRuns.data.total) : recentRuns.error ? '!' : <Skeleton className="mt-1 h-8 w-16" />}
          hint="Awaiting model integration"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Section
          eyebrow="Registry"
          title="Recently registered"
          to="/zebras?sort=-created_at"
          resource={recentZebras}
          empty={{ title: 'No zebras yet', description: 'Registered individuals appear here.' }}
        >
          {(items) =>
            items.map((z) => (
              <Row
                key={z.id}
                to={`/zebras/${z.id}`}
                primary={<span className="font-mono text-accent">{z.code}</span>}
                secondary={`${z.name || 'Unnamed'} · ${timeAgo(z.created_at)}`}
                right={<ZebraStatusBadge status={z.status} />}
              />
            ))
          }
        </Section>

        <Section
          eyebrow="Field"
          title="Recent sightings"
          to="/sightings"
          resource={recentSightings}
          empty={{ title: 'No sightings yet', description: 'Field observations appear here.' }}
        >
          {(items) =>
            items.map((s) => (
              <Row
                key={s.id}
                primary={s.location_name || (s.latitude != null ? `${s.latitude.toFixed(3)}, ${s.longitude.toFixed(3)}` : 'Location not recorded')}
                secondary={`${formatDateTime(s.observed_at)}${s.observer ? ` · ${s.observer}` : ''}`}
                right={<Badge tone={s.zebra_id ? 'success' : 'neutral'}>{s.zebra_id ? 'Identified' : 'Unidentified'}</Badge>}
              />
            ))
          }
        </Section>

        <Section
          eyebrow="Recognition"
          title="Identification activity"
          resource={recentRuns}
          empty={{
            title: 'No identification runs',
            description: 'Runs appear once the recognition model is integrated.',
          }}
        >
          {(items) =>
            items.map((r) => (
              <Row
                key={r.id}
                primary={r.model_name}
                secondary={timeAgo(r.created_at)}
                right={<Badge tone={RUN_TONE[r.status] || 'neutral'} dot>{r.status}</Badge>}
              />
            ))
          }
        </Section>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader eyebrow="Activity" title="Recent activity" description="Latest registrations, uploads, sightings and runs" />
          <ActivityFeed zebras={recentZebras} sightings={recentSightings} runs={recentRuns} images={recentImages} />
        </Card>

        <Card className="self-start">
          <CardHeader
            eyebrow="System"
            title="Service status"
            action={<Badge tone={TONE[api.status] || 'danger'} dot>{api.status}</Badge>}
          />
          <CardBody className="pt-3">
            <dl className="divide-y divide-line">
              <StatusRow label="API base URL">
                <span className="font-mono text-xs text-muted">{API_BASE_URL}</span>
              </StatusRow>
              <StatusRow label="Backend">
                {api.status === 'loading' ? <Skeleton className="h-4 w-14" /> : api.status}
              </StatusRow>
              <StatusRow label="Database">
                {db.status === 'loading' ? (
                  <Skeleton className="h-4 w-20" />
                ) : (
                  <span className="tabular">
                    {db.status}
                    {db.latency_ms != null && <span className="text-muted"> · {db.latency_ms} ms</span>}
                  </span>
                )}
              </StatusRow>
            </dl>
            {db.status === 'error' && (
              <p className="mt-3 rounded-control border border-danger/30 bg-danger/10 p-2.5 text-xs text-danger">
                {db.detail}
              </p>
            )}
          </CardBody>
        </Card>
      </section>
    </div>
  )
}
