import { useEffect, useId, useRef } from 'react'
import { CloseIcon } from '../icons.jsx'
import { Button } from './Button.jsx'

/**
 * Modal built on native <dialog>: focus is trapped and Esc closes it.
 * Controlled: pass `open` and `onClose`. Clicking the backdrop also closes.
 */
export function Dialog({ open, onClose, title, description, children, footer, size = 'md' }) {
  const ref = useRef(null)
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  const width = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' }[size]

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onCancel={(e) => {
        e.preventDefault()
        onClose?.()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose?.()
      }}
      className={`m-auto w-[calc(100%-2rem)] ${width} rounded-card border border-line bg-surface p-0 text-ink shadow-pop`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div>
          <h2 id={titleId} className="text-base font-semibold">
            {title}
          </h2>
          {description && (
            <p id={descId} className="mt-1 text-sm text-muted">
              {description}
            </p>
          )}
        </div>
        <Button variant="ghost" size="icon" aria-label="Close dialog" onClick={onClose} className="-mr-2 -mt-1">
          <CloseIcon className="h-4 w-4" />
        </Button>
      </div>
      <div className="px-5 py-5 text-sm text-muted">{children}</div>
      {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
    </dialog>
  )
}
