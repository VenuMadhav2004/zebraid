import { useSystemStatus } from '../services/useSystemStatus.js'
import { Badge } from './ui/index.js'

const TONE = { ok: 'success', error: 'danger', loading: 'neutral' }

export default function StatusBadge() {
  const { api, db } = useSystemStatus()
  return (
    <div className="flex items-center gap-2">
      {[['API', api], ['Database', db]].map(([label, s]) => (
        <Badge key={label} tone={TONE[s.status] || 'danger'} dot pulse={s.status === 'loading'} title={s.detail || ''}>
          {label}
        </Badge>
      ))}
    </div>
  )
}
