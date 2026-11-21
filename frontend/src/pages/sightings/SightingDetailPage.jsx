import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useImageUrl, useZebra } from '../../components/identify/identifyHelpers.js'
import { SightingsIcon } from '../../components/icons.jsx'
import SightingFormDialog from '../../components/sightings/SightingFormDialog.jsx'
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, EmptyState, ErrorState, Skeleton } from '../../components/ui/index.js'
import { PhotoFrame } from '../../components/zebras/ZebraBits.jsx'
import { useToast } from '../../hooks/toastContext.js'
import { useResource } from '../../hooks/useResource.js'
import { formatDateTime } from '../../lib/format.js'
import { formatCoords } from '../../lib/sightingForm.js'
import { imagesApi, sightingsApi } from '../../services/zebraid.js'

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-2.5 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{children ?? <span className="text-faint">Not recorded</span>}</dd>
    </div>
  )
}

function DeleteDialog({ sighting, onClose }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [deletePhoto, setDeletePhoto] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function confirm() {
    setBusy(true)
    try {
      await sightingsApi.remove(sighting.id)
    } catch (err) {
      setError(err.message)
      setBusy(false)
      return
    }
    let note
    if (deletePhoto && sighting.image_asset_id) {
      await imagesApi.remove(sighting.image_asset_id).catch((err) => {
        note = err.code === 'image_in_use' ? 'Photograph kept: other records use it.' : `Photograph kept: ${err.message}`
      })
    }
    toast({ title: 'Sighting deleted', description: note })
    navigate('/sightings')
  }

  return (
    <ConfirmDialog title="Delete sighting?" description="This permanently removes the observation." confirmLabel="Delete sighting" busy={busy} onClose={onClose} onConfirm={confirm}>
      {sighting.image_asset_id && (
        <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-sm text-ink">
          <input type="checkbox" checked={deletePhoto} disabled={busy} onChange={(e) => setDeletePhoto(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]" />
          Also delete the attached photograph (kept automatically if other records use it)
        </label>
      )}
      {error && <p className="mt-3 text-xs text-danger">{error}</p>}
    </ConfirmDialog>
  )
}

export default function SightingDetailPage() {
  const { sightingId } = useParams()
  const navigate = useNavigate()
  const [version, setVersion] = useState(0)
  const s = useResource(['sighting', sightingId, version], () => sightingsApi.get(sightingId))
  const zebra = useZebra(s.data?.zebra_id)
  const photo = useImageUrl(s.data?.image_asset_id)
  const [dialog, setDialog] = useState(null)

  if (s.error) {
    return (
      <Card>
        {s.error.status === 404 ? (
          <EmptyState title="Sighting not found" description="It may have been deleted." action={<Button variant="secondary" onClick={() => navigate('/sightings')}>Back to sightings</Button>} />
        ) : (
          <ErrorState title="Could not load this sighting" error={s.error} onRetry={s.refetch} />
        )}
      </Card>
    )
  }

  const d = s.data
  const coords = d && formatCoords(d.latitude, d.longitude)

  return (
    <div className="space-y-5">
      <Link to="/sightings" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <span aria-hidden="true">←</span> Sightings
      </Link>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="overflow-hidden">
          {d?.image_asset_id ? (
            <PhotoFrame src={photo.data?.url} loading={photo.loading || !d} eager alt="Sighting photograph" className="aspect-[4/3]" imgClassName="object-contain bg-canvas" />
          ) : (
            <div className="stripe-texture flex aspect-[4/3] flex-col items-center justify-center gap-2 bg-raised text-faint">
              {d ? (
                <>
                  <SightingsIcon className="h-8 w-8" />
                  <span className="text-xs">No photograph attached</span>
                </>
              ) : (
                <Skeleton className="h-full w-full rounded-none" />
              )}
            </div>
          )}
        </Card>

        <Card className="self-start">
          <CardHeader
            eyebrow="Sighting"
            title={d ? formatDateTime(d.observed_at) : <Skeleton className="h-5 w-48" />}
            action={d && (d.zebra_id ? <Badge tone="success" dot>Identified</Badge> : <Badge>Unidentified</Badge>)}
          />
          <CardBody className="pt-2">
            {d ? (
              <dl className="divide-y divide-line">
                <Row label="Zebra">
                  {d.zebra_id ? (
                    <Link to={`/zebras/${d.zebra_id}`} className="font-mono text-accent hover:underline">
                      {zebra.data?.code ?? '…'}
                    </Link>
                  ) : (
                    <span className="text-faint">Not identified</span>
                  )}
                </Row>
                <Row label="Place">{d.location_name}</Row>
                <Row label="Coordinates">{coords && <span className="tabular font-mono text-xs">{coords}</span>}</Row>
                <Row label="Observer">{d.observer}</Row>
                <Row label="Notes">{d.notes && <span className="whitespace-pre-wrap">{d.notes}</span>}</Row>
                {d.identification_run_id && (
                  <Row label="Identification">
                    <Link to={`/identify/runs/${d.identification_run_id}`} className="text-accent hover:underline">
                      View run
                    </Link>
                  </Row>
                )}
                <Row label="Recorded">{formatDateTime(d.created_at)}</Row>
                <Row label="Updated">{formatDateTime(d.updated_at)}</Row>
              </dl>
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-5" />
                ))}
              </div>
            )}
            <div className="mt-5 flex flex-wrap gap-2">
              <Button variant="secondary" disabled={!d || (d.zebra_id && !zebra.data)} onClick={() => setDialog('edit')}>
                Edit sighting
              </Button>
              <Button variant="danger" disabled={!d} onClick={() => setDialog('delete')}>
                Delete
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>

      {dialog === 'edit' && d && (
        <SightingFormDialog sighting={d} zebra={zebra.data ?? null} onClose={() => setDialog(null)} onSaved={() => (setDialog(null), setVersion((v) => v + 1))} />
      )}
      {dialog === 'delete' && d && <DeleteDialog sighting={d} onClose={() => setDialog(null)} />}
    </div>
  )
}
