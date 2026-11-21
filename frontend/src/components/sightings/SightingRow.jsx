import { Link } from 'react-router-dom'
import { formatDateTime, timeAgo } from '../../lib/format.js'
import { formatCoords } from '../../lib/sightingForm.js'
import { useImageUrl, useZebra } from '../identify/identifyHelpers.js'
import { SightingsIcon } from '../icons.jsx'
import { Badge } from '../ui/index.js'
import { PhotoFrame } from '../zebras/ZebraBits.jsx'

export function SightingRow({ sighting: s }) {
  const photo = useImageUrl(s.image_asset_id)
  const zebra = useZebra(s.zebra_id)
  const coords = formatCoords(s.latitude, s.longitude)
  return (
    <li>
      <Link
        to={`/sightings/${s.id}`}
        className="grid grid-cols-[5rem_1fr] gap-4 px-4 py-3.5 transition-colors hover:bg-raised/50 sm:grid-cols-[6rem_minmax(0,1.3fr)_minmax(0,1fr)_auto] sm:items-center"
      >
        {s.image_asset_id ? (
          <PhotoFrame src={photo.data?.url} loading={photo.loading} alt={`Sighting photograph, ${formatDateTime(s.observed_at)}`} className="aspect-[4/3] rounded-md" />
        ) : (
          <div className="stripe-texture flex aspect-[4/3] items-center justify-center rounded-md bg-raised text-faint">
            <SightingsIcon className="h-5 w-5" />
          </div>
        )}
        <div className="min-w-0">
          <div className="truncate text-sm text-ink">{s.location_name || (coords ? 'Unnamed location' : 'Location not recorded')}</div>
          {coords && <div className="tabular truncate font-mono text-[0.6875rem] text-faint">{coords}</div>}
          <time dateTime={s.observed_at} className="mt-0.5 block text-xs text-muted">
            {formatDateTime(s.observed_at)} · {timeAgo(s.observed_at)}
          </time>
        </div>
        <div className="col-span-2 min-w-0 text-xs sm:col-span-1">
          {s.observer && <div className="truncate text-muted">Observer: {s.observer}</div>}
          {s.notes && <div className="truncate text-faint">{s.notes}</div>}
        </div>
        <div className="col-span-2 sm:col-span-1 sm:justify-self-end">
          {s.zebra_id ? (
            <Badge tone="success" dot>
              <span className="font-mono">{zebra.data?.code ?? '…'}</span>
            </Badge>
          ) : (
            <Badge>Unidentified</Badge>
          )}
        </div>
      </Link>
    </li>
  )
}
