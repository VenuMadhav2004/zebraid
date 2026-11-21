import { DECISION_LABEL, DECISION_TONE, RUN_TONE } from './identifyHelpers.js'
import { Badge } from '../ui/index.js'

export function RunStatusBadge({ status }) {
  return (
    <Badge tone={RUN_TONE[status] || 'neutral'} dot pulse={status === 'running'}>
      {status}
    </Badge>
  )
}

export function ReviewBadge({ verification }) {
  if (!verification) return <Badge>Awaiting review</Badge>
  return (
    <Badge tone={DECISION_TONE[verification.decision]} dot>
      {DECISION_LABEL[verification.decision]}
    </Badge>
  )
}

/** Zebra code (registered) or the raw ML label (not registered). */
export function CandidateIdentity({ candidate, zebra }) {
  if (candidate.zebra_id) {
    return <span className="font-mono font-semibold text-accent">{zebra?.code ?? '…'}</span>
  }
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <span className="min-w-0 break-all font-mono text-ink">{candidate.external_label}</span>
      <Badge tone="warning">Unregistered label</Badge>
    </span>
  )
}
