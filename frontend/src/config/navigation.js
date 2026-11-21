import {
  CubeIcon,
  GalleryIcon,
  IdentifyIcon,
  OverviewIcon,
  ReportIcon,
  SightingsIcon,
  SparkleIcon,
  StripesIcon,
} from '../components/icons.jsx'

/**
 * Single source for sidebar entries and top-bar titles.
 * `status` describes availability; no module beyond Overview is functional yet.
 */
export const NAV_SECTIONS = [
  {
    label: 'Research',
    items: [
      { to: '/', end: true, label: 'Overview', icon: OverviewIcon, description: 'Population, activity and system health at a glance' },
      { to: '/identify', label: 'Identify Zebra', icon: IdentifyIcon, description: 'Match a field photo against the reference gallery', status: 'Awaiting model' },
      { to: '/zebras', label: 'Zebra Gallery', icon: GalleryIcon, description: 'Registered individuals and their reference images' },
      { to: '/sightings', label: 'Sightings', icon: SightingsIcon, description: 'Field observations by place and time' },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { to: '/stripes', label: 'Stripe Explorer', icon: StripesIcon, description: 'Inspect stripe morphology, spatial frequency, and visual overlays' },
      { to: '/hide-viewer', label: '3D Hide Viewer', icon: CubeIcon, description: 'Inspect authorized 3D OBJ/MTL zebra hide scans' },
      { to: '/assistant', label: 'Gemini Assistant', icon: SparkleIcon, description: 'Explain actual stripe measurements and research records' },
    ],
  },
]

/** Routes that exist but are not in the sidebar. */
const HIDDEN_ROUTES = [
  { to: '/reports', label: 'Research Reports', icon: ReportIcon, description: 'Exportable research summaries' },
  { to: '/ui', label: 'Design System', icon: OverviewIcon, description: 'Component reference (development only)' },
]

export const ALL_ROUTES = [...NAV_SECTIONS.flatMap((s) => s.items), ...HIDDEN_ROUTES]

export function routeMeta(pathname) {
  return (
    ALL_ROUTES.find((r) => (r.end ? pathname === r.to : pathname === r.to || pathname.startsWith(`${r.to}/`))) ||
    ALL_ROUTES[0]
  )
}
