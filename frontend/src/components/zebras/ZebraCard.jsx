import { Link } from 'react-router-dom'
import { useResource } from '../../hooks/useResource.js'
import { timeAgo } from '../../lib/format.js'
import { IMAGE_URL_TTL, galleryApi } from '../../services/zebraid.js'
import { Card, Skeleton } from '../ui/index.js'
import { PhotoFrame, ZebraStatusBadge } from './ZebraBits.jsx'

/** Card with the zebra's main reference photo (first active gallery entry). */
export function ZebraCard({ zebra }) {
  const photo = useResource(['main-photo', zebra.id], () =>
    galleryApi.list(zebra.id, { limit: 1, include_urls: true, expires_in: IMAGE_URL_TTL }),
  )
  const entry = photo.data?.items?.[0]
  const count = photo.data?.total

  return (
    <Link to={`/zebras/${zebra.id}`} className="group block rounded-card focus-visible:outline-offset-4">
      <Card interactive className="overflow-hidden">
        <PhotoFrame
          src={entry?.image_url?.url}
          alt={`Reference photograph of ${zebra.code}`}
          loading={photo.loading && !photo.data}
          className="aspect-[4/3]"
          imgClassName="transition-transform duration-300 group-hover:scale-[1.03]"
        >
          <div className="absolute left-3 top-3 rounded-full bg-canvas/85 backdrop-blur">
            <ZebraStatusBadge status={zebra.status} />
          </div>
          {count > 0 && (
            <span className="absolute bottom-3 right-3 rounded-full bg-canvas/80 px-2 py-0.5 text-[0.6875rem] text-muted backdrop-blur">
              {count} {count === 1 ? 'photo' : 'photos'}
            </span>
          )}
        </PhotoFrame>
        <div className="px-4 py-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="truncate font-mono text-sm font-semibold tracking-tight text-accent">{zebra.code}</span>
            <span className="shrink-0 text-[0.6875rem] text-faint">{timeAgo(zebra.created_at)}</span>
          </div>
          <div className="mt-1 truncate text-sm text-ink">{zebra.name || <span className="text-faint">Unnamed</span>}</div>
          <div className="mt-0.5 truncate text-xs italic text-muted">{zebra.species || <span className="not-italic text-faint">Species not confirmed</span>}</div>
        </div>
      </Card>
    </Link>
  )
}

export function ZebraCardSkeleton() {
  return (
    <Card className="overflow-hidden">
      <Skeleton className="aspect-[4/3] rounded-none" />
      <div className="space-y-2 px-4 py-3.5">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    </Card>
  )
}
