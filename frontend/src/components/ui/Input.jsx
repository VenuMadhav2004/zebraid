import { useId } from 'react'
import { cn } from '../../lib/cn.js'

const CONTROL =
  'w-full rounded-control border bg-raised px-3 text-sm text-ink placeholder:text-faint transition-colors ' +
  'focus:outline-none focus-visible:outline-none focus:border-accent/70 focus:ring-2 focus:ring-accent/20 ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

function Field({ id, label, hint, error, required, className, children }) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label && (
        <label htmlFor={id} className="text-xs font-medium text-muted">
          {label}
          {required && <span className="ml-0.5 text-accent">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p id={`${id}-msg`} className="text-xs text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-msg`} className="text-xs text-faint">
            {hint}
          </p>
        )
      )}
    </div>
  )
}

function useFieldProps({ id, hint, error }) {
  const generated = useId()
  const fieldId = id || generated
  return {
    fieldId,
    aria: {
      id: fieldId,
      'aria-invalid': error ? true : undefined,
      'aria-describedby': error || hint ? `${fieldId}-msg` : undefined,
    },
    border: error ? 'border-danger/60' : 'border-line hover:border-line-strong',
  }
}

/** Text input with optional label, hint and error message (error wins over hint). */
export function Input({ label, hint, error, required, className, inputClassName, id, ...props }) {
  const { fieldId, aria, border } = useFieldProps({ id, hint, error })
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} required={required} className={className}>
      <input required={required} className={cn(CONTROL, 'h-10', border, inputClassName)} {...aria} {...props} />
    </Field>
  )
}

export function Textarea({ label, hint, error, required, className, rows = 4, id, ...props }) {
  const { fieldId, aria, border } = useFieldProps({ id, hint, error })
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} required={required} className={className}>
      <textarea rows={rows} required={required} className={cn(CONTROL, 'resize-y py-2.5', border)} {...aria} {...props} />
    </Field>
  )
}

export function Select({ label, hint, error, required, className, children, id, ...props }) {
  const { fieldId, aria, border } = useFieldProps({ id, hint, error })
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} required={required} className={className}>
      <select required={required} className={cn(CONTROL, 'h-10 appearance-none pr-8', border)} {...aria} {...props}>
        {children}
      </select>
    </Field>
  )
}
