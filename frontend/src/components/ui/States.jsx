import { cn } from '../../lib/cn.js'
import { AlertIcon, InboxIcon, RefreshIcon } from '../icons.jsx'
import { Button } from './Button.jsx'

function StateFrame({ icon, tone = 'neutral', title, description, children, className }) {
  const ring = tone === 'danger' ? 'border-danger/30 bg-danger/10 text-danger' : 'border-line bg-raised text-accent'
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-12 text-center', className)}>
      <div className={cn('mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border', ring)}>{icon}</div>
      <h3 className="text-[0.9375rem] font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted">{description}</p>}
      {children && <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{children}</div>}
    </div>
  )
}

export function EmptyState({ icon, title = 'Nothing here yet', description, action, className }) {
  return (
    <StateFrame icon={icon || <InboxIcon />} title={title} description={description} className={className}>
      {action}
    </StateFrame>
  )
}

/**
 * Error panel. `error` may be an ApiError from services/api.js (uses message,
 * status and requestId) or any Error; `message` overrides it.
 */
export function ErrorState({ title = 'Something went wrong', error, message, onRetry, className }) {
  const text = message || error?.message || 'The request could not be completed.'
  const requestId = error?.requestId
  return (
    <StateFrame icon={<AlertIcon />} tone="danger" title={title} description={text} className={className}>
      {onRetry && (
        <Button variant="secondary" size="sm" leftIcon={<RefreshIcon className="h-4 w-4" />} onClick={onRetry}>
          Try again
        </Button>
      )}
      {requestId && <span className="font-mono text-[0.6875rem] text-faint">ref {requestId}</span>}
    </StateFrame>
  )
}
