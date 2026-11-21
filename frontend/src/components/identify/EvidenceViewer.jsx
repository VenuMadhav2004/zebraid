import { Link } from 'react-router-dom'
import { Badge, Card, CardBody, CardHeader, EmptyState } from '../ui/index.js'
import { PhotoFrame } from '../zebras/ZebraBits.jsx'
import { IdentifyIcon } from '../icons.jsx'
import { EvidenceTable } from './EvidenceTable.jsx'
import { CandidateIdentity } from './shared.jsx'
import { formatSimilarity, useImageUrl, useZebra } from './identifyHelpers.js'

function Pane({ label, children, footer }) {
  return (
    <figure className="min-w-0">
      <figcaption className="eyebrow mb-2">{label}</figcaption>
      {children}
      {footer && <div className="mt-2 text-xs text-faint">{footer}</div>}
    </figure>
  )
}

/** Local preview before submission. */
export function PreviewViewer({ previewUrl, file }) {
  if (!previewUrl) {
    return (
      <Card className="flex min-h-[28rem] items-center justify-center">
        <EmptyState
          icon={<IdentifyIcon />}
          title="No photograph selected"
          description="Add a field photograph on the left, or open a previous identification from the history below."
        />
      </Card>
    )
  }
  return (
    <Card className="overflow-hidden">
      <CardHeader eyebrow="Preview" title={file?.name} description="Not uploaded yet" />
      <CardBody>
        <div className="overflow-hidden rounded-control border border-line bg-canvas">
          <img src={previewUrl} alt="Query photograph preview" className="mx-auto max-h-[32rem] w-full object-contain" />
        </div>
      </CardBody>
    </Card>
  )
}

/**
 * Query vs selected candidate. The right pane shows the reference image the model
 * reported (matched_reference_image_id). If none was reported it says so; it does
 * not substitute another photo as if it were the match.
 */
export function ComparisonViewer({ run, candidate }) {
  const query = useImageUrl(run.query_image_id)
  const ref = useImageUrl(candidate?.matched_reference_image_id)
  const zebra = useZebra(candidate?.zebra_id)

  return (
    <Card>
      <CardHeader
        eyebrow="Comparison"
        title={candidate ? `Query vs rank ${candidate.rank}` : 'Query photograph'}
        action={
          candidate && (
            <Badge tone="accent" title="Model similarity score. Not a probability.">
              Similarity {formatSimilarity(candidate.similarity_score)}
            </Badge>
          )
        }
      />
      <CardBody className="space-y-5">
        <div className={candidate ? 'grid gap-4 md:grid-cols-2' : ''}>
          <Pane label="Query photograph">
            <PhotoFrame src={query.data?.url} loading={query.loading} eager alt="Query photograph" className="aspect-[4/3] rounded-control" imgClassName="object-contain bg-canvas" />
          </Pane>
          {candidate && (
            <Pane
              label="Matched reference"
              footer={
                candidate.zebra_id && zebra.data ? (
                  <>
                    Gallery photograph of{' '}
                    <Link to={`/zebras/${candidate.zebra_id}`} className="font-mono text-accent hover:underline">
                      {zebra.data.code}
                    </Link>
                  </>
                ) : (
                  <CandidateIdentity candidate={candidate} zebra={zebra.data} />
                )
              }
            >
              {candidate.matched_reference_image_id ? (
                <PhotoFrame src={ref.data?.url} loading={ref.loading} eager alt="Matched reference photograph" className="aspect-[4/3] rounded-control" imgClassName="object-contain bg-canvas" />
              ) : (
                <div className="stripe-texture flex aspect-[4/3] items-center justify-center rounded-control border border-dashed border-line-strong p-6 text-center text-xs text-faint">
                  The model did not report a matched reference image for this candidate.
                </div>
              )}
            </Pane>
          )}
        </div>
        {query.error && <p className="text-xs text-danger">Query image: {query.error.message}</p>}
        {candidate && (
          <section>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 className="text-sm font-semibold text-ink">Evidence</h3>
              {candidate.score_type && <span className="text-xs text-faint">Score type: {candidate.score_type}</span>}
            </div>
            <EvidenceTable evidence={candidate.evidence} />
          </section>
        )}
      </CardBody>
    </Card>
  )
}
