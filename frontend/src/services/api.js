import axios from 'axios'

// "/api" goes through the Vite dev proxy (and the Netlify redirect in production).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

// Versioned API client: requests resolve to `${API_BASE_URL}/v1/...` -> backend /api/v1/...
export const apiV1 = axios.create({
  baseURL: `${API_BASE_URL}/v1`,
  timeout: 15000,
})

/**
 * Normalise every failed request into one Error shape.
 * Backend errors use {"error": {code, message, details, request_id}}.
 */
export function toApiError(err) {
  const res = err.response
  const body = res?.data?.error
  const e = new Error(body?.message || (res ? `HTTP ${res.status}` : err.message || 'Network error'))
  e.status = res?.status ?? null
  e.code = body?.code || (res ? 'http_error' : 'network_error')
  e.details = body?.details ?? null
  e.requestId = body?.request_id || res?.headers?.['x-request-id'] || null
  return e
}

for (const client of [api, apiV1]) {
  client.interceptors.response.use(
    (r) => r,
    (err) => Promise.reject(toApiError(err)),
  )
}

export const getHealth = () => api.get('/health').then((r) => r.data)

// /health/db returns 503 with a JSON body when the DB is unreachable
export const getDbHealth = () =>
  api.get('/health/db', { validateStatus: () => true }).then((r) => r.data)

// GET /api/v1/ -> {name, api_version, app_version}
export const getApiInfo = () => apiV1.get('/').then((r) => r.data)

export default api
