import { useState } from 'react'
import { useToast } from '../../hooks/toastContext.js'
import { blankToNull, fieldErrorsFrom, pruneErrors, validateZebra } from '../../lib/zebraForm.js'
import { zebrasApi } from '../../services/zebraid.js'
import { Button, Dialog } from '../ui/index.js'
import { ZebraFields } from './ZebraFields.jsx'

const FORM_ID = 'edit-zebra-form'
const FIELDS = ['name', 'species', 'sex', 'status', 'notes']

/** PATCH only the fields that changed. The code is immutable in the backend. */
export default function EditZebraDialog({ zebra, onClose, onSaved }) {
  const { toast } = useToast()
  const initial = Object.fromEntries(FIELDS.map((f) => [f, zebra[f] ?? '']))
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    const found = validateZebra(values, { requireCode: false })
    setErrors(found)
    if (Object.keys(found).length) return
    const changes = {}
    for (const f of FIELDS) {
      const next = f === 'status' ? values.status : blankToNull(values[f])
      if (next !== (zebra[f] ?? null)) changes[f] = next
    }
    if (!Object.keys(changes).length) return onClose()
    setBusy(true)
    setFormError(null)
    try {
      const updated = await zebrasApi.update(zebra.id, changes)
      toast({ title: 'Profile updated', description: `${updated.code}: ${Object.keys(changes).join(', ')} changed.` })
      onSaved(updated)
    } catch (err) {
      setErrors(fieldErrorsFrom(err))
      setFormError(err.message)
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      size="lg"
      onClose={busy ? undefined : onClose}
      title={`Edit ${zebra.code}`}
      description="The zebra code cannot be changed."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={busy}>
            Save changes
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
        <ZebraFields values={values} errors={errors} onChange={(next) => (setErrors((e) => pruneErrors(e, values, next)), setValues(next))} disabled={busy} showCode={false} />
        {formError && (
          <p role="alert" className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {formError}
          </p>
        )}
      </form>
    </Dialog>
  )
}
