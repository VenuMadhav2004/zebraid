import { useState } from 'react'
import { useToast } from '../../hooks/toastContext.js'
import { submitVerification } from '../../services/identification.js'
import { Button, Dialog, Input, Textarea } from '../ui/index.js'
import { formatSimilarity } from './identifyHelpers.js'

const REVIEWER_KEY = 'zebraid.reviewer'
const FORM_ID = 'verify-form'

function readReviewer() {
  try {
    return localStorage.getItem(REVIEWER_KEY) || ''
  } catch {
    return ''
  }
}

const COPY = {
  confirmed: {
    title: 'Confirm identity',
    action: 'Confirm identity',
    done: 'Identity confirmed',
    text: (c, code) => `Record that this photograph shows ${code} (rank ${c.rank}, similarity ${formatSimilarity(c.similarity_score)}).`,
  },
  rejected: {
    title: 'Reject candidate',
    action: 'Reject candidate',
    done: 'Rejection recorded',
    text: (c, code) => `Record that this photograph does not show ${code} (rank ${c.rank}).`,
  },
  unknown: {
    title: 'Mark as unknown',
    action: 'Mark unknown',
    done: 'Marked as unknown',
    text: () => 'Record that none of the candidates can be confirmed: the individual is unknown or undecidable. No zebra is created.',
  },
}

/** Human decision. Append-only: a later decision supersedes earlier ones but history is kept. */
export default function VerifyDialog({ run, decision, candidate, candidateLabel, onClose, onSaved }) {
  const { toast } = useToast()
  const [reviewer, setReviewer] = useState(readReviewer)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const copy = COPY[decision]

  async function submit(e) {
    e.preventDefault()
    const name = reviewer.trim()
    if (!name) return setError('Enter your name or initials so the decision is attributable')
    setBusy(true)
    setError(null)
    try {
      const saved = await submitVerification(run.id, { decision, candidateId: candidate?.id, verifiedBy: name, notes })
      try {
        localStorage.setItem(REVIEWER_KEY, name)
      } catch {
        /* storage unavailable: ignore */
      }
      toast({ title: copy.done, description: `By ${name}.` })
      onSaved(saved)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      size="sm"
      onClose={busy ? undefined : onClose}
      title={copy.title}
      description={copy.text(candidate, candidateLabel)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={busy} variant={decision === 'rejected' ? 'danger' : 'primary'}>
            {copy.action}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
        <Input
          label="Reviewer"
          required
          value={reviewer}
          onChange={(e) => (setReviewer(e.target.value), setError(null))}
          maxLength={120}
          placeholder="Name or initials"
          hint="Stored with the decision. No sign-in exists yet."
          disabled={busy}
        />
        <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Optional: what you compared" disabled={busy} />
        <p className="text-xs text-faint">Decisions are append-only. A later decision replaces this one as current, and both stay in the history.</p>
        {error && (
          <p role="alert" className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  )
}
