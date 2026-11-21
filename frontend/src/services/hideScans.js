// Authorized 3D hide scans served read-only by the backend (/api/v1/hide-scans).
import { apiV1 } from './api.js'

export const listHideScans = () => apiV1.get('/hide-scans').then((r) => r.data)

const MIME = { obj: 'text/plain', mtl: 'text/plain' }

/**
 * Download every file of a scan and return browser File objects for the existing viewer pipeline.
 * onProgress({loaded, total}) reports bytes across all files. No timeout: files are tens of MB.
 */
export async function fetchScanFiles(scan, { onProgress, signal } = {}) {
  const total = scan.files.reduce((n, f) => n + f.size_bytes, 0)
  let done = 0
  const out = []
  for (const f of scan.files) {
    const res = await apiV1.get(`/hide-scans/${encodeURIComponent(scan.id)}/files/${encodeURIComponent(f.name)}`, {
      responseType: 'blob',
      timeout: 0,
      signal,
      onDownloadProgress: (ev) => onProgress?.({ loaded: done + (ev.loaded || 0), total }),
    })
    done += f.size_bytes
    onProgress?.({ loaded: done, total })
    const type = f.role === 'texture' ? res.data.type || 'image/png' : MIME[f.role] || 'application/octet-stream'
    out.push(new File([res.data], f.name, { type }))
  }
  return out
}
