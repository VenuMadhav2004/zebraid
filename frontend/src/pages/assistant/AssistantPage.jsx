import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { SparkleIcon } from '../../components/icons.jsx'
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Select, Spinner, Textarea } from '../../components/ui/index.js'
import { useResource } from '../../hooks/useResource.js'
import { buildHistoryPayload, friendlyAssistantError, parseScientificSections } from '../../lib/assistantFormat.js'
import { cn } from '../../lib/cn.js'
import { formatDateTime } from '../../lib/format.js'
import { askAssistant, getAssistantStatus } from '../../services/assistant.js'
import { listAnalyses } from '../../services/stripeAnalysis.js'
import { identificationsApi, imagesApi, zebrasApi } from '../../services/zebraid.js'

const SAMPLE_PROMPTS = [
  'Summarize the observed stripe width, spacing, orientation, and quality metrics from the selected analyses, clearly separating measurements from hypotheses.',
  'Compare the spatial-frequency FFT peak and negative-control spectrum for this image, noting all caveats.',
  'What data is currently recorded in STRIPEFORGE right now, and what additional measurements are needed?',
]

/** Safe inline bold + code renderer (zero dangerouslySetInnerHTML). */
function InlineText({ text }) {
  const tokens = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return tokens.map((tok, idx) => {
    if (tok.startsWith('**') && tok.endsWith('**') && tok.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-ink">
          {tok.slice(2, -2)}
        </strong>
      )
    }
    if (tok.startsWith('`') && tok.endsWith('`') && tok.length > 2) {
      return (
        <code key={idx} className="rounded bg-canvas px-1 py-0.5 font-mono text-[0.75rem] text-accent">
          {tok.slice(1, -1)}
        </code>
      )
    }
    return <span key={idx}>{tok}</span>
  })
}

function FormattedLines({ lines }) {
  return (
    <div className="space-y-1.5 text-sm leading-relaxed text-muted">
      {lines.map((line, i) => {
        const trimmed = line.trim()
        if (!trimmed) return <div key={i} className="h-1" />
        const bullet = trimmed.match(/^[-*•]\s+(.*)$/)
        if (bullet) {
          return (
            <div key={i} className="flex gap-2 pl-1">
              <span aria-hidden="true" className="text-accent">•</span>
              <span className="min-w-0 flex-1 text-ink/90">
                <InlineText text={bullet[1]} />
              </span>
            </div>
          )
        }
        return (
          <p key={i} className="text-ink/90">
            <InlineText text={trimmed} />
          </p>
        )
      })}
    </div>
  )
}

function ScientificAnswer({ text }) {
  const sections = parseScientificSections(text)
  if (!sections.length) return <p className="text-sm text-muted">{text}</p>

  return (
    <div className="space-y-3">
      {sections.map((sec, idx) => {
        if (sec.kind === 'observations') {
          return (
            <div key={idx} className="rounded-control border border-success/30 bg-success/5 p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-ink">{sec.title}</span>
                <Badge tone="success">Observed data</Badge>
              </div>
              <FormattedLines lines={sec.lines} />
            </div>
          )
        }
        if (sec.kind === 'hypotheses') {
          return (
            <div key={idx} className="rounded-control border border-warning/30 bg-warning/5 p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-ink">{sec.title}</span>
                <Badge tone="warning">AI hypothesis</Badge>
              </div>
              <FormattedLines lines={sec.lines} />
            </div>
          )
        }
        return <FormattedLines key={idx} lines={sec.lines} />
      })}
    </div>
  )
}

export default function AssistantPage() {
  const [searchParams] = useSearchParams()
  const initialImage = searchParams.get('image') || ''
  const initialAnalyses = (searchParams.get('analyses') || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const initialZebra = searchParams.get('zebra') || ''
  const initialRun = searchParams.get('run') || ''

  const status = useResource(['assistant-status'], getAssistantStatus)
  const images = useResource(['assistant-images'], () => imagesApi.list({ limit: 50 }))
  const zebras = useResource(['assistant-zebras'], () => zebrasApi.list({ limit: 50 }))
  const runs = useResource(['assistant-runs'], () => identificationsApi.list({ limit: 20 }))

  const [imageId, setImageId] = useState(initialImage)
  const [zebraId, setZebraId] = useState(initialZebra)
  const [runId, setRunId] = useState(initialRun)
  const [analyses, setAnalyses] = useState([])
  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState(initialAnalyses)
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)
  const [errorState, setErrorState] = useState(null) // { message, retryable, failedQuestion }
  const [messages, setMessages] = useState([])

  useEffect(() => {
    if (!imageId) {
      setAnalyses([])
      setSelectedAnalysisIds([])
      return
    }
    let alive = true
    listAnalyses({ image_id: imageId, limit: 10 })
      .then((page) => {
        if (!alive) return
        const items = page.items || []
        setAnalyses(items)
        setSelectedAnalysisIds((prev) => {
          const validPrev = prev.filter((id) => items.some((a) => a.id === id))
          if (validPrev.length) return validPrev
          return items.filter((a) => a.status === 'completed').slice(0, 2).map((a) => a.id)
        })
      })
      .catch(() => {
        if (!alive) return
        setAnalyses([])
        setSelectedAnalysisIds([])
      })
    return () => {
      alive = false
    }
  }, [imageId])

  const available = Boolean(status.data?.available)

  function toggleAnalysis(id) {
    setSelectedAnalysisIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(0, 6)))
  }

  async function sendQuestion(qText) {
    const q = String(qText || '').trim()
    if (q.length < 2 || !available || sending) return
    setSending(true)
    setErrorState(null)
    try {
      const history = buildHistoryPayload(messages)
      const resp = await askAssistant({
        question: q,
        imageId: imageId || undefined,
        analysisIds: selectedAnalysisIds,
        zebraId: zebraId || undefined,
        runId: runId || undefined,
        history,
      })
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}`,
          question: q,
          answer: resp.answer,
          model: resp.model,
          groundedContext: resp.grounded_context,
          at: new Date().toISOString(),
        },
      ])
      setQuestion('')
    } catch (err) {
      const mapped = friendlyAssistantError(err)
      setErrorState({ ...mapped, failedQuestion: q })
    } finally {
      setSending(false)
    }
  }

  function handleSubmit(e) {
    e?.preventDefault()
    sendQuestion(question)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="eyebrow">Grounded explanation</div>
          <h2 className="mt-1 text-xl font-semibold text-ink">Gemini scientific assistant</h2>
          <p className="mt-1 text-sm text-muted">
            Explains actual persisted STRIPEFORGE records and analysis outputs, separating observed measurements from AI hypotheses.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {status.loading ? (
            <Badge tone="neutral">Checking status…</Badge>
          ) : available ? (
            <Badge tone="success" dot>
              Ready · {status.data.model}
            </Badge>
          ) : (
            <Badge tone="warning" dot>
              Unavailable
            </Badge>
          )}
          <Button size="sm" variant="ghost" onClick={status.refetch}>
            Refresh
          </Button>
        </div>
      </div>

      {!status.loading && !available && (
        <Card className="border-warning/40 bg-warning/10 p-4 text-sm">
          <div className="font-semibold text-warning">Gemini assistant is currently unavailable</div>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {status.data?.reason || status.error?.message || 'GEMINI_API_KEY is not configured on the backend.'}
          </p>
          <p className="mt-2 text-xs text-faint">
            No synthetic or mocked answers are generated in offline mode. Configure <span className="font-mono text-ink">GEMINI_API_KEY</span> in{' '}
            <span className="font-mono text-ink">backend/.env</span> and restart FastAPI to enable live grounded responses.
          </p>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-[20rem_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader eyebrow="Evidence scope" title="Grounded records" description="Only selected persisted database records are sent to Gemini." />
          <CardBody className="space-y-3 pt-3">
            <Select label="Stored image" value={imageId} onChange={(e) => setImageId(e.target.value)}>
              <option value="">None selected</option>
              {(images.data?.items || []).map((img) => (
                <option key={img.id} value={img.id}>
                  {img.kind} · {img.width ?? '?'}×{img.height ?? '?'} · {img.id.slice(0, 8)}
                </option>
              ))}
            </Select>

            {imageId && (
              <Link to={`/stripes?image=${imageId}`} className="inline-block text-xs text-accent hover:underline">
                Open image in Stripe Explorer →
              </Link>
            )}

            {analyses.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-xs font-medium text-muted">Analyses to include ({selectedAnalysisIds.length})</div>
                <div className="space-y-1 rounded-control border border-line bg-raised/60 p-2 text-xs">
                  {analyses.map((a) => (
                    <label key={a.id} className="flex cursor-pointer items-start gap-2">
                      <input
                        type="checkbox"
                        checked={selectedAnalysisIds.includes(a.id)}
                        onChange={() => toggleAnalysis(a.id)}
                        className="mt-0.5 accent-[var(--color-accent)]"
                      />
                      <span className="min-w-0">
                        <span className="text-ink">{a.kind === 'stripe_morphology' ? 'Morphology (M1)' : 'Frequency (M2)'}</span>
                        <span className="ml-1 text-faint">({a.status})</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <Select label="Registered zebra" value={zebraId} onChange={(e) => setZebraId(e.target.value)}>
              <option value="">None selected</option>
              {(zebras.data?.items || []).map((z) => (
                <option key={z.id} value={z.id}>
                  {z.code}
                  {z.name ? ` · ${z.name}` : ''}
                </option>
              ))}
            </Select>

            <Select label="Identification run" value={runId} onChange={(e) => setRunId(e.target.value)}>
              <option value="">None selected</option>
              {(runs.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.model_name} · {r.status} · {r.id.slice(0, 8)}
                </option>
              ))}
            </Select>

            <div className="border-t border-line pt-3 space-y-1.5">
              <div className="eyebrow">Suggested questions</div>
              {SAMPLE_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  type="button"
                  disabled={!available || sending}
                  onClick={() => setQuestion(p)}
                  className={cn(
                    'block w-full rounded-control border border-line bg-raised/50 p-2 text-left text-xs text-muted hover:border-line-strong hover:text-ink disabled:opacity-50',
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card className="flex min-w-0 flex-col">
          <CardHeader
            eyebrow="Conversation"
            title="Scientific Q&A"
            description="Observed measurements are strictly separated from AI hypotheses and caveats."
            action={
              messages.length > 0 && (
                <Button size="sm" variant="ghost" disabled={sending} onClick={() => (setMessages([]), setErrorState(null))}>
                  Clear chat
                </Button>
              )
            }
          />
          <CardBody className="flex flex-1 flex-col gap-4 pt-3">
            {messages.length === 0 ? (
              <EmptyState
                className="py-12"
                icon={<SparkleIcon />}
                title="Ask about actual stripe measurements or records"
                description="Select an image, completed analysis, zebra, or identification run on the left to ground Gemini in real persisted data."
              />
            ) : (
              <div className="space-y-4">
                {messages.map((m) => (
                  <div key={m.id} className="space-y-3 rounded-control border border-line bg-raised/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-accent">Researcher question</span>
                      <span className="text-faint">{formatDateTime(m.at)}</span>
                    </div>
                    <p className="text-sm text-ink">{m.question}</p>
                    <div className="border-t border-line pt-3 space-y-3">
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        <Badge tone="info">{m.model}</Badge>
                        <Badge tone="neutral">
                          Context:{' '}
                          {m.groundedContext?.included_records?.length
                            ? m.groundedContext.included_records.join(', ')
                            : 'database summary'}
                        </Badge>
                        {m.groundedContext?.analysis_count > 0 && (
                          <Badge tone="neutral">{m.groundedContext.analysis_count} analysis record(s)</Badge>
                        )}
                        {m.groundedContext?.history_turns > 0 && (
                          <Badge tone="neutral">{m.groundedContext.history_turns} prior turn(s)</Badge>
                        )}
                        {m.groundedContext?.context_truncated && (
                          <Badge tone="warning">Context compacted</Badge>
                        )}
                      </div>
                      <ScientificAnswer text={m.answer} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-auto space-y-3 border-t border-line pt-4">
              <Textarea
                label="Question"
                rows={3}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask Gemini to interpret stripe width, orientation coherence, FFT peaks, or caveats…"
                disabled={!available || sending}
              />
              {errorState && (
                <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  <span>{errorState.message}</span>
                  {errorState.retryable && errorState.failedQuestion && (
                    <Button
                      size="sm"
                      variant="secondary"
                      type="button"
                      disabled={sending}
                      onClick={() => sendQuestion(errorState.failedQuestion)}
                    >
                      Retry
                    </Button>
                  )}
                </div>
              )}
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-faint">
                  {sending ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Spinner className="h-3.5 w-3.5 text-accent" /> Querying Gemini with grounded context…
                    </span>
                  ) : (
                    <span>Multi-turn grounded chat · API key stays server-side</span>
                  )}
                </span>
                <Button type="submit" loading={sending} disabled={!available || question.trim().length < 2 || sending}>
                  Ask Gemini
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
