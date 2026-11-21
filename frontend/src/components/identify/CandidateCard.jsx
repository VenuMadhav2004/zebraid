import { Link } from 'react-router-dom'
import { cn } from '../../lib/cn.js'
import { candidateVerification } from '../../services/identification.js'
import { Badge, Button } from '../ui/index.js'
import { PhotoFrame } from '../zebras/ZebraBits.jsx'
import { CandidateIdentity } from './shared.jsx'
import { DECISION_LABEL, DECISION_TONE, formatSimilarity, useImageUrl, useZebra } from './identifyHelpers.js'

/**
 * One ranked suggestion. `selected` highlights it in the centre comparison.
 * canReview: run is completed. Confirm needs a registered zebra (backend rule).
 */
export function CandidateCard({ candidate, verifications, selected, onSelect, canReview, onDecide }) {
  const zebra = useZebra(candidate.zebra_id)
  const ref = useImageUrl(candidate.matched_reference_image_id)
  const decision = candidateVerification(verifications, candidate.id)
  const evidenceCount = Object.keys(candidate.evidence || {}).length

  return (
    <article
      className={cn(
        'rounded-card border bg-surface transition-colors',
        selected ? 'border-accent/60 shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-accent)_35%,transparent)]' : 'border-line hover:border-line-strong',
      )}
    >
      <button type="button" onClick={onSelect} aria-pressed={selected} className="flex w-full gap-3 p-3 text-left">
        <div className="flex w-9 shrink-0 flex-col items-center">
          <span className="eyebrow">Rank</span>
          <span className="tabular font-display text-xl font-semibold text-ink">{candidate.rank}</span>
        </div>
        <PhotoFrame
          src={ref.data?.url}
          loading={ref.loading}
          alt={candidate.matched_reference_image_id ? 'Matched reference photograph' : ''}
          className="h-16 w-20 shrink-0 rounded-md"
        />
        <div className="min-w-0 flex-1">
          <div className="min-w-0 text-sm">
            <CandidateIdentity candidate={candidate} zebra={zebra.data} />
          </div>
          {zebra.data?.name && <div className="truncate text-xs text-muted">{zebra.data.name}</div>}
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-xs">
            <span className="text-faint" title="Model similarity score. Not a probability.">
              Similarity
            </span>
            <span className="tabular font-mono text-ink">{formatSimilarity(candidate.similarity_score)}</span>
            {candidate.score_type && <span className="truncate text-faint">({candidate.score_type})</span>}
          </div>
        </div>
      </button>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {decision ? (
            <Badge tone={DECISION_TONE[decision.decision]} dot>
              {DECISION_LABEL[decision.decision]}
            </Badge>
          ) : (
            <Badge>Not reviewed</Badge>
          )}
          <span className="text-[0.6875rem] text-faint">
            {evidenceCount ? `${evidenceCount} evidence field${evidenceCount === 1 ? '' : 's'}` : 'No evidence'}
          </span>
        </div>
        <div className="flex gap-1.5">
          {candidate.zebra_id && zebra.data && (
            <Link to={`/zebras/${candidate.zebra_id}`} className="rounded-control px-2 py-1 text-xs text-muted hover:bg-raised hover:text-ink">
              Profile
            </Link>
          )}
          <Button
            size="sm"
            variant="secondary"
            disabled={!canReview}
            onClick={() => onDecide('rejected', candidate)}
            className="hover:text-danger"
          >
            Reject
          </Button>
          <Button
            size="sm"
            disabled={!canReview || !candidate.zebra_id}
            title={!candidate.zebra_id ? 'Register this zebra before it can be confirmed' : undefined}
            onClick={() => onDecide('confirmed', candidate)}
          >
            Confirm
          </Button>
        </div>
      </div>
    </article>
  )
}
