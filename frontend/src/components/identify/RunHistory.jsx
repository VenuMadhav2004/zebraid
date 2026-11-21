import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useResource } from '../../hooks/useResource.js'
import { cn } from '../../lib/cn.js'
import { formatDateTime, timeAgo } from '../../lib/format.js'
import { currentVerification, getCandidates, getVerifications, listRuns } from '../../services/identification.js'
import { Button, Card, CardHeader, EmptyState, ErrorState, Select, Skeleton } from '../ui/index.js'
import { PhotoFrame } from '../zebras/ZebraBits.jsx'
import { CandidateIdentity, ReviewBadge, RunStatusBadge } from './shared.jsx'
import { formatSimilarity, useImageUrl, useZebra } from './identifyHelpers.js'

const PAGE = 10

function TopCandidate({ candidate }) {
  const zebra = useZebra(candidate.zebra_id)
  return (
    <span className="flex min-w-0 items-baseline gap-2 text-xs">
      <span className="truncate">
        <CandidateIdentity candidate={candidate} zebra={zebra.data} />
      </span>
      <span className="tabular shrink-0 font-mono text-faint">{formatSimilarity(candidate.similarity_score)}</span>
    </span>
  )
}

function HistoryRow({ run, active, refreshKey }) {
  const thumb = useImageUrl(run.query_image_id)
  const cands = useResource(['cands', run.id, run.updated_at], () => getCandidates(run.id))
  const verifs = useResource(['verifs', run.id, refreshKey], () => getVerifications(run.id))
  const top = cands.data?.[0]

  return (
    <li>
      <Link
        to={`/identify/runs/${run.id}`}
        aria-current={active ? 'page' : undefined}
        className={cn(
          'grid grid-cols-[4.5rem_1fr] items-center gap-3 px-4 py-3 transition-colors sm:grid-cols-[4.5rem_minmax(0,1.2fr)_minmax(0,1fr)_auto] sm:gap-4',
          active ? 'bg-raised' : 'hover:bg-raised/50',
        )}
      >
        <PhotoFrame src={thumb.data?.url} loading={thumb.loading} alt={`Query photograph thumbnail, ${formatDateTime(run.created_at)}`} className="h-12 w-[4.5rem] rounded-md" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <time dateTime={run.created_at} title={formatDateTime(run.created_at)} className="text-xs text-faint">
              {timeAgo(run.created_at)}
            </time>
          </div>
          <div className="mt-1 truncate text-xs text-muted">{run.model_name}</div>
        </div>
        <div className="col-span-2 min-w-0 sm:col-span-1">
          {cands.loading && !cands.data ? (
            <Skeleton className="h-4 w-32" />
          ) : top ? (
            <>
              <TopCandidate candidate={top} />
              <div className="text-[0.6875rem] text-faint">
                {cands.data.length} candidate{cands.data.length === 1 ? '' : 's'}
              </div>
            </>
          ) : (
            <span className="text-xs text-faint">{run.status === 'completed' ? 'No candidates returned' : '—'}</span>
          )}
        </div>
        <div className="col-span-2 sm:col-span-1 sm:justify-self-end">
          {verifs.data ? <ReviewBadge verification={currentVerification(verifs.data)} /> : <Skeleton className="h-6 w-24" />}
        </div>
      </Link>
    </li>
  )
}

/** refreshKey: bump after a verification so review badges reload. */
export function RunHistory({ activeRunId, refreshKey = 0 }) {
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const params = { status: status || undefined, limit: PAGE, offset }
  const runs = useResource(['runs', params, refreshKey, activeRunId], () => listRuns(params))
  const total = runs.data?.total ?? 0

  return (
    <Card>
      <CardHeader
        eyebrow="History"
        title="Identification history"
        description={runs.data ? `${total} run${total === 1 ? '' : 's'}` : 'Previous identification runs'}
        action={
          <Select aria-label="Filter by status" value={status} onChange={(e) => (setStatus(e.target.value), setOffset(0))} className="w-36">
            <option value="">All statuses</option>
            {['completed', 'pending', 'running', 'failed'].map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </Select>
        }
      />
      <div className="mt-4">
        {runs.error ? (
          <ErrorState title="Could not load history" error={runs.error} onRetry={runs.refetch} />
        ) : !runs.data ? (
          <div className="space-y-3 px-4 pb-4">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : runs.data.items.length === 0 ? (
          <EmptyState
            className="border-t border-line"
            title={status ? `No ${status} runs` : 'No identification runs yet'}
            description="Runs are created by the recognition model. They will be listed here with their candidates and review status."
          />
        ) : (
          <>
            <ul className="divide-y divide-line border-t border-line">
              {runs.data.items.map((r) => (
                <HistoryRow key={r.id} run={r} active={r.id === activeRunId} refreshKey={refreshKey} />
              ))}
            </ul>
            {total > PAGE && (
              <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-muted">
                <span className="tabular">
                  {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
                    Previous
                  </Button>
                  <Button size="sm" variant="secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  )
}
