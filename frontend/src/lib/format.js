const dateFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const rel = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

export const formatDate = (iso) => (iso ? dateFmt.format(new Date(iso)) : '—')
export const formatDateTime = (iso) => (iso ? dateTimeFmt.format(new Date(iso)) : '—')

export function timeAgo(iso) {
  if (!iso) return '—'
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000
  const steps = [
    [60, 'second'],
    [60, 'minute'],
    [24, 'hour'],
    [7, 'day'],
    [4.35, 'week'],
    [12, 'month'],
    [Infinity, 'year'],
  ]
  let value = seconds
  for (const [size, unit] of steps) {
    if (Math.abs(value) < size) return rel.format(Math.round(value), unit)
    value /= size
  }
  return formatDate(iso)
}

export function formatBytes(n) {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export const formatCount = (n) => (n == null ? '—' : new Intl.NumberFormat().format(n))
