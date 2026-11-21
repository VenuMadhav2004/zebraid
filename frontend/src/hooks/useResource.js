import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Minimal data loader (TanStack Query is not part of this project).
 * `key` is any JSON-serialisable value; the fetcher re-runs whenever it changes.
 * Pass key = null to skip. Stale responses from older keys are ignored.
 */
export function useResource(key, fetcher) {
  const serial = key === null ? null : JSON.stringify(key)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const [state, setState] = useState({ data: undefined, error: null, loading: serial !== null })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (serial === null) return
    let active = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fetcherRef
      .current()
      .then((data) => active && setState({ data, error: null, loading: false }))
      .catch((error) => active && setState((s) => ({ data: s.data, error, loading: false })))
    return () => {
      active = false
    }
  }, [serial, tick])

  const refetch = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, refetch }
}

/** Value that follows `value` after `delay` ms without changes. */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}
