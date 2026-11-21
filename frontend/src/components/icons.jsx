// Line icons on a 24px grid, 1.6px stroke, inheriting currentColor.
import { cn } from '../lib/cn.js'

function Icon({ className, children, ...props }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={cn('h-5 w-5 shrink-0', className)}
      {...props}
    >
      {children}
    </svg>
  )
}

export const OverviewIcon = (p) => (
  <Icon {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="4.5" rx="1.5" />
    <rect x="13.5" y="11" width="7" height="9.5" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
  </Icon>
)

export const IdentifyIcon = (p) => (
  <Icon {...p}>
    <path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" />
    <circle cx="12" cy="12" r="3.5" />
    <path d="m14.6 14.6 2.4 2.4" />
  </Icon>
)

export const GalleryIcon = (p) => (
  <Icon {...p}>
    <rect x="3.5" y="6.5" width="13" height="13" rx="2" />
    <path d="M7.5 3.5h11a2 2 0 0 1 2 2v11" />
    <path d="m3.5 16 3.6-3.6a1.5 1.5 0 0 1 2.1 0l4.8 4.8" />
    <circle cx="12.5" cy="10.5" r="1.25" />
  </Icon>
)

export const SightingsIcon = (p) => (
  <Icon {...p}>
    <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
    <circle cx="12" cy="10" r="2.4" />
  </Icon>
)

export const StripesIcon = (p) => (
  <Icon {...p}>
    <path d="M3.5 6c2.5-1.6 4.5 1.6 7 0s4.5-1.6 7 0 2.5 1 3 .6" />
    <path d="M3.5 12c2.5-1.6 4.5 1.6 7 0s4.5-1.6 7 0 2.5 1 3 .6" />
    <path d="M3.5 18c2.5-1.6 4.5 1.6 7 0s4.5-1.6 7 0 2.5 1 3 .6" />
  </Icon>
)

export const CubeIcon = (p) => (
  <Icon {...p}>
    <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z" />
    <path d="M4 7.5 12 12l8-4.5M12 12v9" />
  </Icon>
)

export const SparkleIcon = (p) => (
  <Icon {...p}>
    <path d="M12 3.5c.5 3.9 2.6 6 6.5 6.5-3.9.5-6 2.6-6.5 6.5-.5-3.9-2.6-6-6.5-6.5 3.9-.5 6-2.6 6.5-6.5Z" />
    <path d="M18.5 15.5c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5Z" />
  </Icon>
)

export const ReportIcon = (p) => (
  <Icon {...p}>
    <path d="M6.5 3.5h7l4 4v13h-11a1.5 1.5 0 0 1-1.5-1.5V5a1.5 1.5 0 0 1 1.5-1.5Z" />
    <path d="M13.5 3.5v4h4M8.5 12.5h7M8.5 16h5" />
  </Icon>
)

export const MenuIcon = (p) => (
  <Icon {...p}>
    <path d="M4 7h16M4 12h16M4 17h10" />
  </Icon>
)

export const CloseIcon = (p) => (
  <Icon {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Icon>
)

export const AlertIcon = (p) => (
  <Icon {...p}>
    <path d="M10.3 4.2 2.9 17.5A2 2 0 0 0 4.6 20.5h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" />
    <path d="M12 9.5v4M12 17h.01" />
  </Icon>
)

export const InboxIcon = (p) => (
  <Icon {...p}>
    <path d="M3.5 13.5 6 5.5h12l2.5 8v5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5v-5Z" />
    <path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5" />
  </Icon>
)

export const ArrowRightIcon = (p) => (
  <Icon {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
)

export const RefreshIcon = (p) => (
  <Icon {...p}>
    <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4" />
  </Icon>
)

/** Brand mark: three tapered stripes in a rounded shield. */
export function BrandMark({ className }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('h-8 w-8', className)}>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--color-raised)" stroke="var(--color-line-strong)" />
      <path d="M8 9.5c4.5-2 9.5-2 16 0-5.5.6-10.8 1.6-16 3.4Z" fill="var(--color-accent)" />
      <path d="M8 16c5-2.2 10.4-2.2 16 0-5.4.7-10.6 1.8-16 3.5Z" fill="var(--color-ink)" opacity="0.9" />
      <path d="M8 22.5c4.5-2 9.5-2 16 0-5.5.6-10.8 1.6-16 3.4Z" fill="var(--color-ink)" opacity="0.55" />
    </svg>
  )
}
