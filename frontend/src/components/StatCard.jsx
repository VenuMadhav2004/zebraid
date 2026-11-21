import { Card } from './ui/index.js'

export default function StatCard({ label, value, hint, icon: Icon }) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div className="eyebrow">{label}</div>
        {Icon && <Icon className="h-4 w-4 text-faint" />}
      </div>
      <div className="tabular mt-3 font-display text-3xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-1.5 text-xs text-faint">{hint}</div>}
    </Card>
  )
}
