import { useLocation } from 'react-router-dom'
import { routeMeta } from '../config/navigation.js'
import { Badge, Card, EmptyState } from '../components/ui/index.js'

/** Shell for modules that are not built yet. Title/description/icon come from navigation config. */
export default function PlaceholderPage({ title }) {
  const { pathname } = useLocation()
  const meta = routeMeta(pathname)
  const Icon = meta.icon

  return (
    <Card className="stripe-texture">
      <EmptyState
        className="py-20"
        icon={<Icon />}
        title={title || meta.label}
        description={meta.description}
        action={<Badge tone="accent">{meta.status || 'In preparation'}</Badge>}
      />
    </Card>
  )
}
