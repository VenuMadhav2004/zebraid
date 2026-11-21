import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CandidateCard } from '../../components/identify/CandidateCard.jsx'
import { ComparisonViewer, PreviewViewer } from '../../components/identify/EvidenceViewer.jsx'
import { RunHistory } from '../../components/identify/RunHistory.jsx'
import { RunSummary } from '../../components/identify/RunSummary.jsx'
import { DECISION_LABEL, DECISION_TONE, useZebra } from '../../components/identify/identifyHelpers.js'
import { UploadPanel } from '../../components/identify/UploadPanel.jsx'
import VerifyDialog from '../../components/identify/VerifyDialog.jsx'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Skeleton } from '../../components/ui/index.js'
import { useResource } from '../../hooks/useResource.js'
import { formatDateTime } from '../../lib/format.js'
import {
  MlUnavailableError,
  currentVerification,
  getCandidates,
  getMlCapability,
  getRun,
  getVerifications,
  submitIdentification,
} from '../../services/identification.js'

/** Object URL + decoded dimensions for the selected local file. */
function useLocalImage(file) {
  const [state, setState] = useState({ url: null, meta: null })
  useEffect(() => {
    if (!file) {
      setState({ url: null, meta: null })
      return
    }
    const url = URL.createObjectURL(file)
    let active = true
    setState({ url, meta: null })
    const img = new Image()
    img.onload = () => active && setState({ url, meta: { width: img.naturalWidth, height: img.naturalHeight } })
    img.onerror = () => active && setState({ url, meta: { error: 'This file could not be decoded as an image.' } })
    img.src = url
    return () => {
      active = false
      URL.revokeObjectURL(url)
    }
  }, [file])
  return state
}

function CurrentDecision({ verification, candidates }) {
  const cand = candidates?.find((c) => c.id === verification?.candidate_id)
  const zebra = useZebra(verification?.decision === 'confirmed' ? verification.zebra_id : null)
  if (!verification) {
    return <p className="text-xs text-faint">No decision recorded. Human verification is required before an identity is accepted.</p>
  }
  return (
    <div className="space-y-1 text-xs">
      <Badge tone={DECISION_TONE[verification.decision]} dot>
        {DECISION_LABEL[verification.decision]}
        {verification.decision === 'confirmed' && zebra.data ? ` as ${zebra.data.code}` : ''}
        {verification.decision === 'rejected' && cand ? ` rank ${cand.rank}` : ''}
      </Badge>
      <p className="text-faint">
        By {verification.verified_by} · {formatDateTime(verification.created_at)}
      </p>
      {verification.notes && <p className="text-muted">“{verification.notes}”</p>}
    </div>
  )
}

function CandidatesPanel({ run, candidates, verifications, selectedId, onSelect, onDecide }) {
  const canReview = run?.status === 'completed'
  const current = currentVerification(verifications.data)
  return (
    <Card className="flex min-w-0 flex-col">
      <CardHeader
        eyebrow="Ranked candidates"
        title="Suggestions"
        description="Ordered by the model. Similarity is not a probability."
      />
      <div className="space-y-3 p-4">
        {!run ? (
          <EmptyState className="py-10" title="No results yet" description="Ranked candidates appear here after an identification run." />
        ) : candidates.error ? (
          <ErrorState className="py-8" title="Could not load candidates" error={candidates.error} onRetry={candidates.refetch} />
        ) : !candidates.data ? (
          Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-28" />)
        ) : candidates.data.length === 0 ? (
          <EmptyState
            className="py-8"
            title={run.status === 'completed' ? 'No candidates returned' : `Run is ${run.status}`}
            description={
              run.status === 'completed'
                ? 'The model returned no gallery matches for this photograph.'
                : run.status === 'failed'
                  ? 'The run failed; see the error on the left.'
                  : 'Candidates will appear when the run completes.'
            }
          />
        ) : (
          candidates.data.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              verifications={verifications.data}
              selected={c.id === selectedId}
              onSelect={() => onSelect(c.id)}
              canReview={canReview}
              onDecide={onDecide}
            />
          ))
        )}
      </div>
      {run && (
        <div className="mt-auto space-y-3 border-t border-line p-4">
          <div className="eyebrow">Review</div>
          {verifications.error ? (
            <p className="text-xs text-danger">{verifications.error.message}</p>
          ) : (
            <CurrentDecision verification={current} candidates={candidates.data} />
          )}
          <Button variant="secondary" className="w-full" disabled={!canReview} onClick={() => onDecide('unknown', null)}>
            Mark as unknown individual
          </Button>
          {!canReview && <p className="text-[0.6875rem] text-faint">Only completed runs can be reviewed.</p>}
        </div>
      )}
    </Card>
  )
}

export default function IdentifyPage() {
  const { runId } = useParams()
  const navigate = useNavigate()

  // Capability (ML availability)
  const [capability, setCapability] = useState(null)
  useEffect(() => {
    let active = true
    getMlCapability().then((c) => active && setCapability(c))
    return () => {
      active = false
    }
  }, [])
  const retryCapability = () => {
    setCapability(null)
    getMlCapability({ refresh: true }).then(setCapability)
  }
  // While the backend is loading the checkpoint in the background, refresh its state every 5 s.
  const modelState = capability?.model_state
  useEffect(() => {
    if (!capability?.available || (modelState !== 'loading' && modelState !== 'idle')) return
    const id = setInterval(() => getMlCapability({ refresh: true }).then(setCapability), 5000)
    return () => clearInterval(id)
  }, [capability?.available, modelState])

  // New submission
  const [file, setFile] = useState(null)
  const [capturedAt, setCapturedAt] = useState('')
  const local = useLocalImage(file)
  const [submit, setSubmit] = useState({ state: 'idle', progress: 0, error: null })

  async function onSubmit() {
    setSubmit({ state: 'uploading', progress: 0, error: null })
    try {
      const run = await submitIdentification(file, {
        capturedAt: capturedAt ? new Date(capturedAt).toISOString() : undefined,
        onUploadProgress: (ev) => ev.total && setSubmit((s) => ({ ...s, progress: Math.round((ev.loaded / ev.total) * 100) })),
        onUploaded: () => setSubmit((s) => ({ ...s, state: 'identifying' })),
      })
      setSubmit({ state: 'idle', progress: 0, error: null })
      setFile(null)
      navigate(`/identify/runs/${run.id}`)
    } catch (err) {
      if (err instanceof MlUnavailableError) setCapability({ available: false, reason: err.message })
      setSubmit({ state: 'error', progress: 0, error: err.message })
    }
  }

  // Existing run
  const [reviewVersion, setReviewVersion] = useState(0)
  const run = useResource(runId ? ['run', runId] : null, () => getRun(runId))
  const candidates = useResource(runId ? ['run-cands', runId] : null, () => getCandidates(runId))
  const verifications = useResource(runId ? ['run-verifs', runId, reviewVersion] : null, () => getVerifications(runId))
  const [selected, setSelected] = useState({ runId: null, candidateId: null })
  const selectedId = selected.runId === runId ? selected.candidateId : candidates.data?.[0]?.id
  const selectedCandidate = candidates.data?.find((c) => c.id === selectedId)

  const [decision, setDecision] = useState(null) // {decision, candidate}
  const decisionZebra = useZebra(decision?.candidate?.zebra_id)
  const candidateLabel = decision?.candidate
    ? decisionZebra.data?.code || decision.candidate.external_label || `rank ${decision.candidate.rank}`
    : ''

  const runData = runId ? run.data : null

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[19rem_minmax(0,1fr)_22rem]">
        {/* Left: intake or run details (min-w-0: let wide content scroll inside, not widen the grid) */}
        <div className="min-w-0 space-y-4">
          {runId ? (
            run.error ? (
              <Card>
                <ErrorState
                  title={run.error.status === 404 ? 'Run not found' : 'Could not load run'}
                  error={run.error}
                  onRetry={run.error.status === 404 ? undefined : run.refetch}
                />
              </Card>
            ) : runData ? (
              <RunSummary
                run={runData}
                actions={
                  <Button variant="secondary" onClick={() => navigate('/identify')}>
                    New identification
                  </Button>
                }
              />
            ) : (
              <Card className="space-y-3 p-4">
                <Skeleton className="h-5 w-32" />
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-4" />
                ))}
              </Card>
            )
          ) : (
            <UploadPanel
              file={file}
              meta={local.meta}
              onFile={(f) => (setFile(f), setSubmit({ state: 'idle', progress: 0, error: null }))}
              capturedAt={capturedAt}
              onCapturedAt={setCapturedAt}
              capability={capability}
              onRetryCapability={retryCapability}
              submit={submit}
              onSubmit={onSubmit}
            />
          )}
        </div>

        {/* Centre: photograph / comparison / evidence */}
        <div className="min-w-0">
          {runId ? (
            runData ? (
              <ComparisonViewer run={runData} candidate={selectedCandidate} />
            ) : run.error ? null : (
              <Skeleton className="h-[28rem]" />
            )
          ) : (
            <PreviewViewer previewUrl={local.url} file={file} />
          )}
        </div>

        {/* Right: ranked candidates + review */}
        <CandidatesPanel
          run={runData}
          candidates={candidates}
          verifications={verifications}
          selectedId={selectedId}
          onSelect={(id) => setSelected({ runId, candidateId: id })}
          onDecide={(d, c) => setDecision({ decision: d, candidate: c })}
        />
      </div>

      <RunHistory activeRunId={runId} refreshKey={reviewVersion} />

      {decision && runData && (
        <VerifyDialog
          run={runData}
          decision={decision.decision}
          candidate={decision.candidate}
          candidateLabel={candidateLabel}
          onClose={() => setDecision(null)}
          onSaved={() => (setDecision(null), setReviewVersion((v) => v + 1))}
        />
      )}
    </div>
  )
}
