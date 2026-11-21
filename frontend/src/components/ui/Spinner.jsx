import { cn } from '../../lib/cn.js'

export function Spinner({ className, label = 'Loading' }) {
  return (
    <span role="status" aria-label={label} className={cn('inline-block h-4 w-4', className)}>
      <svg viewBox="0 0 24 24" className="h-full w-full animate-spin" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
        <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    </span>
  )
}

/** Placeholder block shown while content loads. Size it with className (h-*, w-*). */
export function Skeleton({ className }) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-control bg-raised', className)} />
}

export function LoadingState({ label = 'Loading…', className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-12 text-sm text-muted', className)}>
      <Spinner className="h-6 w-6 text-accent" label={label} />
      <span>{label}</span>
    </div>
  )
}
