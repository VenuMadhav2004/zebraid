import { useCallback, useMemo, useState } from 'react'
import { ToastContext } from '../../hooks/toastContext.js'
import { cn } from '../../lib/cn.js'
import { AlertIcon, CloseIcon } from '../icons.jsx'

const TONES = {
  success: 'border-success/35',
  danger: 'border-danger/40',
  info: 'border-line-strong',
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 text-success" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12.2 2.4 2.3 4.6-4.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => setToasts((all) => all.filter((t) => t.id !== id)), [])
  const toast = useCallback(
    ({ title, description, tone = 'success', duration = 5000 }) => {
      const id = Math.random().toString(36).slice(2)
      setToasts((all) => [...all.slice(-3), { id, title, description, tone }])
      setTimeout(() => dismiss(id), duration)
    },
    [dismiss],
  )
  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === 'danger' ? 'alert' : 'status'}
            className={cn('pointer-events-auto flex gap-3 rounded-card border bg-surface p-3.5 shadow-pop', TONES[t.tone])}
          >
            {t.tone === 'danger' ? <AlertIcon className="text-danger" /> : <CheckIcon />}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-ink">{t.title}</div>
              {t.description && <div className="mt-0.5 text-xs leading-relaxed text-muted">{t.description}</div>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="-mr-1 -mt-1 h-7 w-7 rounded-control text-faint hover:bg-raised hover:text-ink"
            >
              <CloseIcon className="mx-auto h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
