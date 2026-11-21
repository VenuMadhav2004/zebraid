import { cn } from '../../lib/cn.js'

const TONES = {
  neutral: 'border-line bg-raised text-muted',
  accent: 'border-accent/35 bg-accent/10 text-accent',
  success: 'border-success/30 bg-success/10 text-success',
  warning: 'border-warning/30 bg-warning/10 text-warning',
  danger: 'border-danger/30 bg-danger/10 text-danger',
  info: 'border-info/30 bg-info/10 text-info',
}

const DOTS = {
  neutral: 'bg-faint',
  accent: 'bg-accent',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
}

/** tone: neutral | accent | success | warning | danger | info. dot adds a status dot (pulse: animate it). */
export function Badge({ tone = 'neutral', dot = false, pulse = false, className, children, ...props }) {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap',
        TONES[tone],
        className,
      )}
      {...props}
    >
      {dot && <span aria-hidden="true" className={cn('h-1.5 w-1.5 rounded-full', DOTS[tone], pulse && 'animate-pulse')} />}
      {children}
    </span>
  )
}
