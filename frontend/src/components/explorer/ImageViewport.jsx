import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '../../lib/cn.js'

const MAX_SCALE = 32
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

/**
 * Zoom / pan / region-of-interest viewport. All ROI values are integer image pixels.
 *
 * Props:
 *   src, naturalSize {width,height}       image to show (size from the decoded image)
 *   tool: 'pan' | 'roi'
 *   roi, onRoiChange(roi|null)            controlled ROI {x,y,width,height}
 *   onViewChange({scale})                 current zoom (1 = 100%)
 *   onCursor({x,y}|null)                  pointer position in image pixels
 *   resetSignal                           change it to re-fit the view
 *   command {type:'zoomIn'|'zoomOut'|'actual', n}  one-off view commands
 */
export function ImageViewport({ src, naturalSize, tool, roi, onRoiChange, onViewChange, onCursor, resetSignal, command, overlay, className }) {
  const box = useRef(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [view, setView] = useState({ scale: 1, x: 0, y: 0, fitted: false })
  const pointers = useRef(new Map())
  const gesture = useRef(null)

  // Track viewport size.
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const fitScale = naturalSize && size.w ? Math.min(size.w / naturalSize.width, size.h / naturalSize.height) * 0.96 : 1
  const minScale = Math.min(fitScale * 0.5, 1)

  const fit = useCallback(() => {
    if (!naturalSize || !size.w) return
    const s = fitScale
    setView({ scale: s, x: (size.w - naturalSize.width * s) / 2, y: (size.h - naturalSize.height * s) / 2, fitted: true })
  }, [naturalSize, size.w, size.h, fitScale])

  // Fit on new image, on reset, and on first measurement.
  useEffect(() => {
    fit()
  }, [src, resetSignal, fit])

  useEffect(() => {
    onViewChange?.({ scale: view.scale, fitScale })
  }, [view.scale, fitScale, onViewChange])

  const zoomAt = useCallback(
    (factor, px, py) =>
      setView((v) => {
        const scale = clamp(v.scale * factor, minScale, MAX_SCALE)
        const k = scale / v.scale
        return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k, fitted: false }
      }),
    [minScale],
  )

  // Toolbar commands. A command issued before this viewport mounted (e.g. for a
  // previous image) must not be replayed, so remember the one seen at mount.
  const handledCommand = useRef(command?.n)
  useEffect(() => {
    if (!command || !size.w || command.n === handledCommand.current) return
    handledCommand.current = command.n
    const cx = size.w / 2
    const cy = size.h / 2
    if (command.type === 'zoomIn') zoomAt(1.4, cx, cy)
    if (command.type === 'zoomOut') zoomAt(1 / 1.4, cx, cy)
    if (command.type === 'actual') setView((v) => zoomAtValue(v, 1, cx, cy))
  }, [command, size.w, size.h, zoomAt])

  // Wheel zoom needs a non-passive listener to prevent page scroll.
  useEffect(() => {
    const el = box.current
    if (!el) return
    const onWheel = (e) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  const toImage = (clientX, clientY) => {
    const r = box.current.getBoundingClientRect()
    return { x: (clientX - r.left - view.x) / view.scale, y: (clientY - r.top - view.y) / view.scale }
  }
  const clampToImage = (p) => ({ x: clamp(Math.round(p.x), 0, naturalSize.width), y: clamp(Math.round(p.y), 0, naturalSize.height) })

  function onPointerDown(e) {
    if (!naturalSize) return
    box.current.setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      gesture.current = { type: 'pinch', dist: Math.hypot(a.x - b.x, a.y - b.y) }
      return
    }
    if (tool === 'roi') {
      const start = clampToImage(toImage(e.clientX, e.clientY))
      gesture.current = { type: 'roi', start }
      onRoiChange(null)
    } else {
      gesture.current = { type: 'pan', last: { x: e.clientX, y: e.clientY } }
    }
  }

  function onPointerMove(e) {
    if (naturalSize) {
      const p = toImage(e.clientX, e.clientY)
      const inside = p.x >= 0 && p.y >= 0 && p.x < naturalSize.width && p.y < naturalSize.height
      onCursor?.(inside ? { x: Math.floor(p.x), y: Math.floor(p.y) } : null)
    }
    if (!pointers.current.has(e.pointerId)) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const g = gesture.current
    if (!g) return
    if (g.type === 'pinch' && pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      const r = box.current.getBoundingClientRect()
      zoomAt(dist / g.dist, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top)
      g.dist = dist
    } else if (g.type === 'pan') {
      const dx = e.clientX - g.last.x
      const dy = e.clientY - g.last.y
      g.last = { x: e.clientX, y: e.clientY }
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy, fitted: false }))
    } else if (g.type === 'roi') {
      const end = clampToImage(toImage(e.clientX, e.clientY))
      const x = Math.min(g.start.x, end.x)
      const y = Math.min(g.start.y, end.y)
      g.rect = { x, y, width: Math.abs(end.x - g.start.x), height: Math.abs(end.y - g.start.y) }
      onRoiChange(g.rect)
    }
  }

  function onPointerUp(e) {
    pointers.current.delete(e.pointerId)
    const g = gesture.current
    if (g?.type === 'roi' && (!g.rect || g.rect.width < 2 || g.rect.height < 2)) onRoiChange(null)
    gesture.current = pointers.current.size === 1 && g?.type === 'pinch' ? { type: 'pan', last: [...pointers.current.values()][0] } : null
  }

  function onKeyDown(e) {
    const cx = size.w / 2
    const cy = size.h / 2
    const step = 40
    const map = {
      '+': () => zoomAt(1.25, cx, cy),
      '=': () => zoomAt(1.25, cx, cy),
      '-': () => zoomAt(0.8, cx, cy),
      0: fit,
      ArrowLeft: () => setView((v) => ({ ...v, x: v.x + step })),
      ArrowRight: () => setView((v) => ({ ...v, x: v.x - step })),
      ArrowUp: () => setView((v) => ({ ...v, y: v.y + step })),
      ArrowDown: () => setView((v) => ({ ...v, y: v.y - step })),
      Escape: () => onRoiChange(null),
    }
    if (map[e.key]) {
      e.preventDefault()
      map[e.key]()
    }
  }

  const r = roi && {
    left: view.x + roi.x * view.scale,
    top: view.y + roi.y * view.scale,
    width: roi.width * view.scale,
    height: roi.height * view.scale,
  }

  return (
    <div
      ref={box}
      tabIndex={0}
      role="application"
      aria-label="Image viewer. Drag to pan or select a region, scroll or pinch to zoom, plus and minus keys zoom, 0 fits, Escape clears the region."
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={() => onCursor?.(null)}
      onKeyDown={onKeyDown}
      className={cn(
        'relative touch-none select-none overflow-hidden bg-canvas focus-visible:outline-offset-[-2px]',
        tool === 'roi' ? 'cursor-crosshair' : 'cursor-grab active:cursor-grabbing',
        className,
      )}
      style={{
        backgroundImage:
          'linear-gradient(45deg, var(--color-surface) 25%, transparent 25%, transparent 75%, var(--color-surface) 75%), linear-gradient(45deg, var(--color-surface) 25%, transparent 25%, transparent 75%, var(--color-surface) 75%)',
        backgroundSize: '24px 24px',
        backgroundPosition: '0 0, 12px 12px',
      }}
    >
      {src && naturalSize && (
        <img
          src={src}
          alt="Image under analysis"
          draggable={false}
          className="pointer-events-none absolute left-0 top-0 max-w-none origin-top-left"
          style={{
            width: naturalSize.width,
            height: naturalSize.height,
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
            imageRendering: view.scale >= 3 ? 'pixelated' : 'auto',
            visibility: view.fitted || view.scale !== 1 ? 'visible' : 'hidden',
          }}
        />
      )}
      {overlay?.url && naturalSize && (
        <img
          src={overlay.url}
          alt={overlay.label || 'Analysis overlay'}
          draggable={false}
          className="pointer-events-none absolute left-0 top-0 max-w-none origin-top-left"
          style={{
            width: overlay.bounds?.width ?? naturalSize.width,
            height: overlay.bounds?.height ?? naturalSize.height,
            transform: `translate(${view.x + (overlay.bounds?.x ?? 0) * view.scale}px, ${view.y + (overlay.bounds?.y ?? 0) * view.scale}px) scale(${view.scale})`,
            opacity: overlay.opacity ?? 0.65,
            imageRendering: view.scale >= 3 ? 'pixelated' : 'auto',
            visibility: view.fitted || view.scale !== 1 ? 'visible' : 'hidden',
          }}
        />
      )}
      {r && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute border border-accent"
          style={{ ...r, boxShadow: '0 0 0 9999px rgb(10 12 11 / 0.55)' }}
        >
          <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-accent px-1.5 py-0.5 font-mono text-[0.625rem] text-accent-ink">
            {roi.width} × {roi.height}
          </span>
        </div>
      )}
    </div>
  )
}

function zoomAtValue(v, scale, px, py) {
  const k = scale / v.scale
  return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k, fitted: false }
}
