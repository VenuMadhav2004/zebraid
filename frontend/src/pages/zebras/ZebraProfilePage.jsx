import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { GalleryIcon } from '../../components/icons.jsx'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorState,
  Skeleton,
} from '../../components/ui/index.js'
import AddPhotoDialog from '../../components/zebras/AddPhotoDialog.jsx'
import EditZebraDialog from '../../components/zebras/EditZebraDialog.jsx'
import { PhotoFrame, ZebraStatusBadge } from '../../components/zebras/ZebraBits.jsx'
import { useToast } from '../../hooks/toastContext.js'
import { useResource } from '../../hooks/useResource.js'
import { formatBytes, formatDate, formatDateTime, timeAgo } from '../../lib/format.js'
import { IMAGE_URL_TTL, galleryApi, imagesApi, zebrasApi } from '../../services/zebraid.js'

const GALLERY_LIMIT = 100

function Detail({ label, children }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-2.5 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{children ?? <span className="text-faint">Not recorded</span>}</dd>
    </div>
  )
}

function Checkbox({ checked, onChange, children, disabled }) {
  return (
    <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-sm text-ink">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]"
      />
      <span>{children}</span>
    </label>
  )
}

/** Full-size view. Fetches a fresh signed URL so it works even after page URLs expire. */
function PhotoLightbox({ entry, zebra, onClose }) {
  const url = useResource(['image-url', entry.image_asset_id], () => imagesApi.url(entry.image_asset_id, IMAGE_URL_TTL))
  const img = entry.image
  return (
    <Dialog open size="lg" onClose={onClose} title={`${zebra.code} · reference photograph`} description={`Added ${formatDateTime(entry.created_at)}`}>
      <PhotoFrame
        src={url.data?.url}
        loading={url.loading}
        eager
        alt={`Reference photograph of ${zebra.code}`}
        className="-mx-1 aspect-[4/3] rounded-control"
        imgClassName="object-contain bg-canvas"
      />
      {url.error && <p className="mt-2 text-xs text-danger">{url.error.message}</p>}
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-4">
        {[
          ['Flank', entry.side],
          ['Dimensions', img.width && img.height ? `${img.width} × ${img.height}` : '—'],
          ['Size', formatBytes(img.size_bytes)],
          ['Format', img.content_type.replace('image/', '').toUpperCase()],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="text-faint">{k}</dt>
            <dd className="text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {entry.quality_notes && <p className="mt-3 text-xs text-muted">{entry.quality_notes}</p>}
    </Dialog>
  )
}

function RemovePhotoDialog({ entry, onClose, onDone }) {
  const { toast } = useToast()
  const [deleteFile, setDeleteFile] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await galleryApi.remove(entry.id)
    } catch (err) {
      setError(err.message)
      setBusy(false)
      return
    }
    if (deleteFile) {
      try {
        await imagesApi.remove(entry.image_asset_id)
        toast({ title: 'Photograph deleted', description: 'Removed from the gallery and from storage.' })
      } catch (err) {
        toast({
          tone: 'danger',
          title: 'Removed from gallery; file kept',
          description: err.code === 'image_in_use' ? 'The image is still used by other records.' : err.message,
        })
      }
    } else {
      toast({ title: 'Removed from gallery', description: 'The image file was kept.' })
    }
    onDone()
  }

  return (
    <ConfirmDialog
      title="Remove photograph?"
      description="It will no longer be part of this zebra's reference gallery."
      confirmLabel="Remove"
      busy={busy}
      onClose={onClose}
      onConfirm={confirm}
    >
      <Checkbox checked={deleteFile} onChange={setDeleteFile} disabled={busy}>
        Also delete the image file from storage
      </Checkbox>
      {error && <p className="mt-3 text-xs text-danger">{error}</p>}
    </ConfirmDialog>
  )
}

function DeleteZebraDialog({ zebra, entries, onClose }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [deletePhotos, setDeletePhotos] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const n = entries.length

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await zebrasApi.remove(zebra.id) // gallery links are removed with the zebra
    } catch (err) {
      setError(
        err.code === 'zebra_in_use'
          ? 'This zebra is referenced by sightings or identification records, so it cannot be deleted. Set its status to inactive or deceased instead.'
          : err.message,
      )
      setBusy(false)
      return
    }
    let kept = 0
    if (deletePhotos) {
      const results = await Promise.allSettled(entries.map((e) => imagesApi.remove(e.image_asset_id)))
      kept = results.filter((r) => r.status === 'rejected').length
    }
    toast({
      title: `${zebra.code} deleted`,
      description: kept ? `${kept} photograph(s) kept because other records use them.` : undefined,
    })
    navigate('/zebras')
  }

  return (
    <ConfirmDialog
      title={`Delete ${zebra.code}?`}
      description="This permanently removes the profile and its gallery links. It cannot be undone."
      confirmLabel="Delete zebra"
      busy={busy}
      onClose={onClose}
      onConfirm={confirm}
    >
      {n > 0 && (
        <Checkbox checked={deletePhotos} onChange={setDeletePhotos} disabled={busy}>
          Also delete its {n} photograph{n === 1 ? '' : 's'} from storage
        </Checkbox>
      )}
      {error && (
        <p role="alert" className="mt-3 rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
    </ConfirmDialog>
  )
}

function GalleryTile({ entry, primary, onView, onRemove }) {
  const img = entry.image
  return (
    <Card className="overflow-hidden">
      <button type="button" onClick={onView} className="block w-full" aria-label="View photograph">
        <PhotoFrame src={entry.image_url?.url} alt="Gallery photograph" className="aspect-[4/3]">
          <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5 [&>*]:bg-canvas/85 [&>*]:backdrop-blur">
            {primary && <Badge tone="accent">Primary</Badge>}
            {!entry.is_active && <Badge>Inactive</Badge>}
            {img.kind === 'crop' && <Badge tone="info">Crop</Badge>}
          </div>
        </PhotoFrame>
      </button>
      <div className="flex items-center justify-between gap-2 px-3.5 py-3">
        <div className="min-w-0 text-xs">
          <div className="text-ink">
            {entry.side === 'unknown' ? 'Flank not set' : `${entry.side[0].toUpperCase()}${entry.side.slice(1)} flank`}
          </div>
          <div className="truncate text-faint">
            {img.width && img.height ? `${img.width}×${img.height} · ` : ''}
            {formatBytes(img.size_bytes)} · {timeAgo(entry.created_at)}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onRemove} className="text-danger hover:text-danger">
          Remove
        </Button>
      </div>
    </Card>
  )
}

export default function ZebraProfilePage() {
  const { zebraId } = useParams()
  const navigate = useNavigate()
  const zebra = useResource(['zebra', zebraId], () => zebrasApi.get(zebraId))
  const gallery = useResource(['gallery', zebraId], () =>
    galleryApi.list(zebraId, { include_inactive: true, include_urls: true, expires_in: IMAGE_URL_TTL, limit: GALLERY_LIMIT }),
  )
  const [dialog, setDialog] = useState(null) // {type, entry?}
  const [override, setOverride] = useState(null) // zebra after a successful edit
  const close = () => setDialog(null)

  if (zebra.error) {
    return (
      <Card>
        {zebra.error.status === 404 ? (
          <EmptyState
            title="Zebra not found"
            description="It may have been deleted."
            action={
              <Button variant="secondary" onClick={() => navigate('/zebras')}>
                Back to gallery
              </Button>
            }
          />
        ) : (
          <ErrorState title="Could not load this zebra" error={zebra.error} onRetry={zebra.refetch} />
        )}
      </Card>
    )
  }

  const z = override?.id === zebraId ? override : zebra.data
  const entries = gallery.data?.items ?? []
  const primary = entries.find((e) => e.is_active)

  return (
    <div className="space-y-5">
      <Link to="/zebras" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <span aria-hidden="true">←</span> Zebra gallery
      </Link>

      <Card className="overflow-hidden">
        <div className="grid md:grid-cols-[minmax(0,22rem)_1fr]">
          <PhotoFrame
            src={primary?.image_url?.url}
            loading={gallery.loading && !gallery.data}
            eager
            alt={z ? `Primary reference photograph of ${z.code}` : ''}
            className="aspect-[4/3] md:aspect-auto md:min-h-64"
          />
          <div className="stripe-texture flex flex-col justify-between gap-6 p-6">
            {z ? (
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="font-mono text-2xl font-semibold tracking-tight text-accent">{z.code}</h2>
                  <ZebraStatusBadge status={z.status} />
                </div>
                <p className="mt-1.5 text-lg text-ink">{z.name || <span className="text-faint">Unnamed individual</span>}</p>
                <p className="mt-0.5 text-sm italic text-muted">{z.species || <span className="not-italic text-faint">Species not confirmed</span>}</p>
                <p className="mt-3 text-xs text-faint">
                  Registered {formatDate(z.created_at)} · {entries.length} gallery photograph{entries.length === 1 ? '' : 's'}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <Skeleton className="h-8 w-40" />
                <Skeleton className="h-5 w-56" />
                <Skeleton className="h-4 w-32" />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setDialog({ type: 'add' })} disabled={!z}>
                Add photograph
              </Button>
              <Button variant="secondary" onClick={() => setDialog({ type: 'edit' })} disabled={!z}>
                Edit details
              </Button>
              <Button variant="danger" onClick={() => setDialog({ type: 'delete' })} disabled={!z || !gallery.data}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <Card className="self-start">
          <CardHeader eyebrow="Profile" title="Details" />
          <CardBody className="pt-2">
            {z ? (
              <dl className="divide-y divide-line">
                <Detail label="Code">
                  <span className="font-mono">{z.code}</span>
                </Detail>
                <Detail label="Name">{z.name}</Detail>
                <Detail label="Species">{z.species && <i>{z.species}</i>}</Detail>
                <Detail label="Sex">{z.sex}</Detail>
                <Detail label="Status">
                  <ZebraStatusBadge status={z.status} />
                </Detail>
                <Detail label="Notes">{z.notes && <span className="whitespace-pre-wrap">{z.notes}</span>}</Detail>
                {Object.keys(z.attributes || {}).length > 0 && (
                  <Detail label="Attributes">
                    <pre className="overflow-x-auto rounded-control bg-raised p-2 font-mono text-xs text-muted">
                      {JSON.stringify(z.attributes, null, 2)}
                    </pre>
                  </Detail>
                )}
                <Detail label="Registered">{formatDateTime(z.created_at)}</Detail>
                <Detail label="Updated">{formatDateTime(z.updated_at)}</Detail>
              </dl>
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-5" />
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            eyebrow="Reference gallery"
            title="Photographs"
            description="Reference images used to recognise this individual. The first active photograph is the primary."
            action={
              gallery.data?.total > GALLERY_LIMIT && <Badge>Showing {GALLERY_LIMIT} of {gallery.data.total}</Badge>
            }
          />
          <CardBody>
            {gallery.error ? (
              <ErrorState title="Could not load photographs" error={gallery.error} onRetry={gallery.refetch} />
            ) : !gallery.data ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="aspect-[4/3]" />
                ))}
              </div>
            ) : entries.length === 0 ? (
              <EmptyState
                icon={<GalleryIcon />}
                title="No reference photographs"
                description="Add a clear side view of the flank. Photographs are stored privately."
                action={<Button onClick={() => setDialog({ type: 'add' })}>Add photograph</Button>}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {entries.map((e) => (
                  <GalleryTile
                    key={e.id}
                    entry={e}
                    primary={e.id === primary?.id}
                    onView={() => setDialog({ type: 'view', entry: e })}
                    onRemove={() => setDialog({ type: 'remove', entry: e })}
                  />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {dialog?.type === 'add' && z && (
        <AddPhotoDialog zebra={z} onClose={close} onAdded={() => (close(), gallery.refetch())} />
      )}
      {dialog?.type === 'edit' && z && (
        <EditZebraDialog zebra={z} onClose={close} onSaved={(updated) => (setOverride(updated), close())} />
      )}
      {dialog?.type === 'view' && z && <PhotoLightbox entry={dialog.entry} zebra={z} onClose={close} />}
      {dialog?.type === 'remove' && (
        <RemovePhotoDialog entry={dialog.entry} onClose={close} onDone={() => (close(), gallery.refetch())} />
      )}
      {dialog?.type === 'delete' && z && <DeleteZebraDialog zebra={z} entries={entries} onClose={close} />}
    </div>
  )
}
