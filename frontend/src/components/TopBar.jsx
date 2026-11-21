import { useLocation } from 'react-router-dom'
import { routeMeta } from '../config/navigation.js'
import { MenuIcon } from './icons.jsx'
import StatusBadge from './StatusBadge.jsx'

export default function TopBar({ onMenu, menuOpen }) {
  const { pathname } = useLocation()
  const meta = routeMeta(pathname)

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        aria-expanded={menuOpen}
        aria-controls="mobile-sidebar"
        className="-ml-1 rounded-control p-2 text-muted hover:bg-raised hover:text-ink md:hidden"
      >
        <MenuIcon />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[0.9375rem] font-semibold text-ink">{meta.label}</h1>
        <p className="hidden truncate text-xs text-faint sm:block">{meta.description}</p>
      </div>
      <StatusBadge />
    </header>
  )
}
