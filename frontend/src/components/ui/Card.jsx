import { cn } from '../../lib/cn.js'

export function Card({ className, children, interactive = false, ...props }) {
  return (
    <section
      className={cn(
        'rounded-card border border-line bg-surface shadow-card',
        interactive && 'transition-colors hover:border-line-strong',
        className,
      )}
      {...props}
    >
      {children}
    </section>
  )
}

export function CardHeader({ eyebrow, title, description, action, className }) {
  return (
    <header className={cn('flex items-start justify-between gap-4 px-5 pt-5', className)}>
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        {title && <h2 className="text-[0.9375rem] font-semibold text-ink">{title}</h2>}
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  )
}

export function CardBody({ className, children }) {
  return <div className={cn('px-5 py-5', className)}>{children}</div>
}

export function CardFooter({ className, children }) {
  return (
    <footer className={cn('flex items-center justify-end gap-2 border-t border-line px-5 py-3.5', className)}>
      {children}
    </footer>
  )
}
