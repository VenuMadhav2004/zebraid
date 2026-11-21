import { useEffect, useId, useRef, useState } from 'react'
import { cn } from '../../lib/cn.js'
import { formatBytes } from '../../lib/format.js'
import { ALLOWED_IMAGE_TYPES, checkImageFile } from '../../services/zebraid.js'
import { CloseIcon, GalleryIcon } from '../icons.jsx'
import { Button } from '../ui/index.js'

/**
 * Pick one photograph (click or drag & drop) with a local preview.
 * Calls onChange(file | null). Shows client-side validation; the server re-checks bytes.
 */
export function ImagePicker({ file, onChange, error, disabled, label = 'Reference photograph', hint }) {
  const inputId = useId()
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [localError, setLocalError] = useState(null)
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    if (!file) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  function accept(f) {
    const problem = checkImageFile(f)
    setLocalError(problem)
    onChange(problem ? null : f)
  }

  const shownError = error || localError

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted">{label}</span>
      {file && preview ? (
        <div className="flex items-center gap-4 rounded-control border border-line bg-raised p-3">
          <img src={preview} alt="Selected photograph preview" className="h-20 w-28 rounded-md object-cover" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm text-ink">{file.name}</div>
            <div className="text-xs text-faint">
              {file.type.replace('image/', '').toUpperCase()} · {formatBytes(file.size)}
            </div>
          </div>
          <Button variant="ghost" size="icon" aria-label="Remove photograph" disabled={disabled} onClick={() => onChange(null)}>
            <CloseIcon className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault()
            if (!disabled) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            if (!disabled && e.dataTransfer.files?.[0]) accept(e.dataTransfer.files[0])
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-control border border-dashed px-4 py-7 text-center transition-colors',
            dragging ? 'border-accent bg-accent/5' : 'border-line-strong bg-raised/50 hover:border-accent/60',
            shownError && 'border-danger/60',
            disabled && 'pointer-events-none opacity-50',
          )}
        >
          <GalleryIcon className="h-6 w-6 text-accent" />
          <span className="text-sm text-ink">Drop a photograph or click to browse</span>
          <span className="text-xs text-faint">{hint || 'JPEG, PNG or WebP · up to 10 MB · clear side view of the flank'}</span>
        </label>
      )}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ALLOWED_IMAGE_TYPES.join(',')}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          if (e.target.files?.[0]) accept(e.target.files[0])
          e.target.value = ''
        }}
      />
      {shownError && <p className="text-xs text-danger">{shownError}</p>}
    </div>
  )
}
