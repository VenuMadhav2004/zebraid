import { useState } from 'react'
import { useResource } from '../../hooks/useResource.js'
import { timeAgo } from '../../lib/format.js'
import { imagesApi } from '../../services/zebraid.js'
import { useImageUrl } from '../identify/identifyHelpers.js'
import { Badge, Button, Dialog, EmptyState, ErrorState, Select, Skeleton } from '../ui/index.js'
import { PhotoFrame } from '../zebras/ZebraBits.jsx'

const PAGE = 12

function Tile({ image, onPick }) {
  const url = useImageUrl(image.id)
  return (
    <button type="button" onClick={() => onPick(image)} className="group overflow-hidden rounded-control border border-line text-left hover:border-accent/60">
      <PhotoFrame src={url.data?.url} loading={url.loading} alt={`${image.kind} image`} className="aspect-[4/3]" />
      <div className="flex items-center justify-between gap-2 px-2 py-1.5">
        <Badge>{image.kind}</Badge>
        <span className="truncate text-[0.625rem] text-faint">
          {image.width && image.height ? `${image.width}×${image.height} · ` : ''}
          {timeAgo(image.created_at)}
        </span>
      </div>
    </button>
  )
}

export default function LibraryPickerDialog({ onPick, onClose }) {
  const [kind, setKind] = useState('')
  const [offset, setOffset] = useState(0)
  const params = { kind: kind || undefined, limit: PAGE, offset }
  const list = useResource(['library', params], () => imagesApi.list(params))
  const total = list.data?.total ?? 0

  return (
    <Dialog open size="lg" onClose={onClose} title="Open from image library" description="Stored photographs (private; shown through short-lived links).">
      <div className="mb-4 flex items-end justify-between gap-3">
        <Select label="Kind" value={kind} onChange={(e) => (setKind(e.target.value), setOffset(0))} className="w-40">
          <option value="">All kinds</option>
          <option value="query">Query</option>
          <option value="reference">Reference</option>
          <option value="crop">Crop</option>
        </Select>
        {list.data && <span className="text-xs text-faint">{total} image{total === 1 ? '' : 's'}</span>}
      </div>
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.refetch} />
      ) : !list.data ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="aspect-[4/3]" />
          ))}
        </div>
      ) : list.data.items.length === 0 ? (
        <EmptyState title="No images stored" description="Upload photographs from the gallery, sightings or this explorer." />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {list.data.items.map((img) => (
            <Tile key={img.id} image={img} onPick={onPick} />
          ))}
        </div>
      )}
      {total > PAGE && (
        <div className="mt-4 flex justify-end gap-2">
          <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
            Previous
          </Button>
          <Button size="sm" variant="secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      )}
    </Dialog>
  )
}
