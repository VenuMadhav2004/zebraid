import { useState } from 'react'
import { ArrowRightIcon, SparkleIcon } from '../components/icons.jsx'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Select,
  Skeleton,
  Textarea,
} from '../components/ui/index.js'

const SWATCHES = [
  ['canvas', '#101312'],
  ['surface', '#1D2421'],
  ['raised', '#252D29'],
  ['line', '#313B36'],
  ['ink', '#E8E4D9'],
  ['muted', '#A3AAA4'],
  ['faint', '#78807A'],
  ['accent', '#C9A66B'],
]

/** Development-only reference of the design system (route /ui, not in the sidebar). */
export default function DesignSystemPage() {
  const [open, setOpen] = useState(false)

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader eyebrow="Tokens" title="Colour" />
        <CardBody className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          {SWATCHES.map(([name, hex]) => (
            <div key={name}>
              <div className="h-14 rounded-control border border-line" style={{ background: `var(--color-${name})` }} />
              <div className="mt-2 text-xs text-ink">{name}</div>
              <div className="font-mono text-[0.6875rem] text-faint">{hex}</div>
            </div>
          ))}
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader eyebrow="Typography" title="Manrope display, Inter text" />
          <CardBody className="space-y-2">
            <h1 className="text-3xl font-semibold">Grevy&apos;s zebra ZB-0042</h1>
            <h2 className="text-xl font-semibold">Reference gallery</h2>
            <p className="text-sm leading-relaxed text-muted">
              Secondary text for descriptions and supporting detail, set in Inter.
            </p>
            <div className="eyebrow">Eyebrow label</div>
            <div className="tabular font-mono text-sm text-muted">similarity 0.8123</div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader eyebrow="Actions" title="Buttons and badges" />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button rightIcon={<ArrowRightIcon className="h-4 w-4" />}>Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger">Danger</Button>
              <Button loading>Saving</Button>
              <Button variant="secondary" size="icon" aria-label="Assistant">
                <SparkleIcon className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge>Neutral</Badge>
              <Badge tone="accent">Candidate</Badge>
              <Badge tone="success" dot>Confirmed</Badge>
              <Badge tone="warning" dot>Pending review</Badge>
              <Badge tone="danger" dot>Rejected</Badge>
              <Badge tone="info">Left flank</Badge>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader eyebrow="Forms" title="Inputs" />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Input label="Zebra code" placeholder="ZB-0001" hint="Letters, digits, . _ -" required />
            <Input label="Name" defaultValue="Kito" error="Name already in use" />
            <Select label="Status" defaultValue="active">
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
            <Input label="Disabled" disabled placeholder="Read only" />
            <Textarea className="sm:col-span-2" label="Notes" placeholder="Field notes" rows={3} />
          </CardBody>
          <CardFooter>
            <Button variant="ghost">Cancel</Button>
            <Button onClick={() => setOpen(true)}>Open dialog</Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader eyebrow="Feedback" title="Loading, empty and error" />
          <CardBody className="space-y-3">
            <div className="flex gap-3">
              <Skeleton className="h-16 w-16" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            </div>
          </CardBody>
          <LoadingState label="Loading gallery…" className="py-6" />
          <div className="grid border-t border-line sm:grid-cols-2">
            <EmptyState className="py-8" title="No sightings" description="Record a field observation to begin." />
            <ErrorState
              className="py-8"
              error={{ message: 'Storage service request failed', requestId: 'a1b2c3d4' }}
              onRetry={() => {}}
            />
          </div>
        </Card>
      </div>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Confirm identity"
        description="Human verification is required before an identity is recorded."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setOpen(false)}>Confirm</Button>
          </>
        }
      >
        This dialog is a component preview. No data is changed.
      </Dialog>
    </div>
  )
}
