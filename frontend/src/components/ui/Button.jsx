import { cn } from '../../lib/cn.js'
import { Spinner } from './Spinner.jsx'

const VARIANTS = {
  primary:
    'bg-accent text-accent-ink hover:bg-accent-strong shadow-[0_8px_24px_-12px_color-mix(in_srgb,var(--color-accent)_60%,transparent)]',
  secondary: 'bg-raised text-ink border border-line hover:border-line-strong hover:bg-line',
  ghost: 'text-muted hover:text-ink hover:bg-raised',
  danger: 'border border-danger/40 text-danger hover:bg-danger/10',
}

const SIZES = {
  sm: 'h-8 gap-1.5 px-3 text-xs',
  md: 'h-10 gap-2 px-4 text-sm',
  lg: 'h-12 gap-2.5 px-5 text-[0.9375rem]',
  icon: 'h-9 w-9 justify-center',
}

/**
 * variant: primary | secondary | ghost | danger
 * size: sm | md | lg | icon (icon-only: pass aria-label)
 * loading: shows a spinner and disables the button
 */
export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  leftIcon,
  rightIcon,
  className,
  children,
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex select-none items-center justify-center rounded-control font-medium tracking-[-0.005em] transition-colors duration-150',
        'disabled:pointer-events-none disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? <Spinner className="h-4 w-4" /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  )
}
