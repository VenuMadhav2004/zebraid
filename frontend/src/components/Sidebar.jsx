import { NavLink } from 'react-router-dom'
import { cn } from '../lib/cn.js'
import { NAV_SECTIONS } from '../config/navigation.js'
import { BrandMark, CloseIcon } from './icons.jsx'

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <BrandMark />
      <div className="leading-tight">
        <div className="font-display text-[0.9375rem] font-bold tracking-tight text-ink">ZebraID</div>
        <div className="text-[0.6875rem] text-faint">Wildlife Intelligence</div>
      </div>
    </div>
  )
}

function NavItem({ item, onNavigate }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-control px-3 py-2 text-sm transition-colors',
          isActive ? 'bg-raised text-ink' : 'text-muted hover:bg-raised/60 hover:text-ink',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            aria-hidden="true"
            className={cn(
              'absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-accent transition-opacity',
              isActive ? 'opacity-100' : 'opacity-0',
            )}
          />
          <Icon className={cn('h-[18px] w-[18px]', isActive ? 'text-accent' : 'text-faint group-hover:text-muted')} />
          <span className="flex-1 truncate">{item.label}</span>
          {item.status && (
            <span className="rounded-full border border-line px-1.5 py-px text-[0.625rem] text-faint">
              {item.status === 'Planned' ? 'Soon' : 'Model'}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

function SidebarContent({ onNavigate }) {
  return (
    <div className="flex h-full flex-col">
      <div className="stripe-texture flex h-16 items-center border-b border-line px-5">
        <Brand />
      </div>
      <nav aria-label="Main" className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="eyebrow mb-2 px-3">{section.label}</div>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavItem key={item.to} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-line px-5 py-4 text-[0.6875rem] leading-relaxed text-faint">
        Identity suggestions require human verification.
      </div>
    </div>
  )
}

/** Fixed rail on md+; slide-over drawer below md (controlled by `open`). */
export default function Sidebar({ open, onClose }) {
  return (
    <>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-line bg-surface md:block">
        <SidebarContent />
      </aside>

      <div className={cn('fixed inset-0 z-40 md:hidden', open ? 'pointer-events-auto' : 'pointer-events-none')}>
        <div
          aria-hidden="true"
          onClick={onClose}
          className={cn('absolute inset-0 bg-canvas/80 backdrop-blur-sm transition-opacity', open ? 'opacity-100' : 'opacity-0')}
        />
        <aside
          id="mobile-sidebar"
          aria-label="Navigation"
          aria-hidden={!open}
          inert={!open}
          className={cn(
            'absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-line bg-surface shadow-pop transition-transform duration-200',
            open ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="absolute right-3 top-4 rounded-control p-1.5 text-muted hover:bg-raised hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
          <SidebarContent onNavigate={onClose} />
        </aside>
      </div>
    </>
  )
}
