import { useState } from 'react'
import { cn } from '../../lib/cn.js'
import { GalleryIcon } from '../icons.jsx'
import { Badge, Skeleton } from '../ui/index.js'

const STATUS_TONE = { active: 'success', inactive: 'neutral', deceased: 'warning' }

export function ZebraStatusBadge({ status }) {
  return (
    <Badge tone={STATUS_TONE[status] || 'neutral'} dot>
      {status}
    </Badge>
  )
}

/**
 * Image frame for private Storage photos. `src` is a short-lived signed URL.
 * Shows a skeleton while the URL is pending (`loading`) and while the bytes download;
 * a neutral placeholder when there is no photo or it fails to load.
 * eager: load immediately (above the fold / dialogs) instead of lazily.
 */
export function PhotoFrame({ src, alt, loading, eager = false, className, imgClassName, children }) {
  // Track load/failure per src so a new URL resets the state without an effect.
  const [loadedSrc, setLoadedSrc] = useState(null)
  const [failedSrc, setFailedSrc] = useState(null)
  const failed = src && failedSrc === src
  const showImg = src && !failed && !loading
  return (
    <div className={cn('relative overflow-hidden bg-raised', className)}>
      {showImg ? (
        <>
          {loadedSrc !== src && <Skeleton className="absolute inset-0 rounded-none" />}
          <img
            src={src}
            alt={alt}
            loading={eager ? 'eager' : 'lazy'}
            decoding="async"
            onLoad={() => setLoadedSrc(src)}
            onError={() => setFailedSrc(src)}
            className={cn(
              'relative h-full w-full object-cover transition-opacity duration-300',
              loadedSrc === src ? 'opacity-100' : 'opacity-0',
              imgClassName,
            )}
          />
        </>
      ) : loading ? (
        <Skeleton className="absolute inset-0 rounded-none" />
      ) : (
        <div className="stripe-texture flex h-full w-full flex-col items-center justify-center gap-2 text-faint">
          <GalleryIcon className="h-7 w-7" />
          <span className="text-[0.6875rem]">{failed ? 'Image unavailable' : 'No reference photo'}</span>
        </div>
      )}
      {children}
    </div>
  )
}
