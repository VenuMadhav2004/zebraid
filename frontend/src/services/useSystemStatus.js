import { useEffect, useState } from 'react'
import { getDbHealth, getHealth } from './api.js'

export function useSystemStatus() {
  const [api, setApi] = useState({ status: 'loading' })
  const [db, setDb] = useState({ status: 'loading' })

  useEffect(() => {
    getHealth().then(setApi).catch((e) => setApi({ status: 'error', detail: e.message }))
    getDbHealth().then(setDb).catch((e) => setDb({ status: 'error', detail: e.message }))
  }, [])

  return { api, db }
}
