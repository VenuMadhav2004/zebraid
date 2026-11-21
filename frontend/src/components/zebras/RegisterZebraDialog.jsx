import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../../hooks/toastContext.js'
import { blankToNull, fieldErrorsFrom, pruneErrors, validateZebra } from '../../lib/zebraForm.js'
import { FLANK_SIDES, addReferencePhoto, zebrasApi } from '../../services/zebraid.js'
import { Button, Dialog, Select } from '../ui/index.js'
import { ImagePicker } from './ImagePicker.jsx'
import { ZebraFields } from './ZebraFields.jsx'

const EMPTY = { code: '', name: '', species: '', sex: '', status: 'active', notes: '' }
const FORM_ID = 'register-zebra-form'

/**
 * Creates the zebra, then (optionally) uploads the reference photo and links it
 * to the gallery. If the photo step fails the zebra still exists: the user is
 * told and taken to its profile to retry the upload there.
 */
export default function RegisterZebraDialog({ onClose, onRegistered }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [values, setValues] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [file, setFile] = useState(null)
  const [side, setSide] = useState('unknown')
  const [step, setStep] = useState(null) // null | 'profile' | 'photo'
  const [progress, setProgress] = useState(0)
  const [formError, setFormError] = useState(null)
  const busy = step !== null

  async function submit(e) {
    e.preventDefault()
    const found = validateZebra(values)
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length) return

    let zebra
    try {
      setStep('profile')
      zebra = await zebrasApi.create({
        code: values.code.trim(),
        name: blankToNull(values.name),
        species: blankToNull(values.species),
        sex: blankToNull(values.sex),
        status: values.status,
        notes: blankToNull(values.notes),
      })
    } catch (err) {
      setErrors(fieldErrorsFrom(err))
      setFormError(err.message)
      setStep(null)
      return
    }

    if (file) {
      try {
        setStep('photo')
        await addReferencePhoto(zebra.id, file, { side }, (ev) => ev.total && setProgress(Math.round((ev.loaded / ev.total) * 100)))
      } catch (err) {
        toast({
          tone: 'danger',
          title: `${zebra.code} registered, photo not saved`,
          description: `${err.message}. Add the photograph from the profile page.`,
        })
        onRegistered?.(zebra)
        navigate(`/zebras/${zebra.id}`)
        return
      }
    }

    toast({ title: `${zebra.code} registered`, description: file ? 'Profile and reference photograph saved.' : 'Profile saved.' })
    onRegistered?.(zebra)
    navigate(`/zebras/${zebra.id}`)
  }

  return (
    <Dialog
      open
      size="lg"
      onClose={busy ? undefined : onClose}
      title="Register zebra"
      description="Create a profile for a known individual. Profiles are created by researchers, never by the model."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={busy}>
            {step === 'photo' ? `Uploading ${progress}%` : step === 'profile' ? 'Saving…' : 'Register zebra'}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-5">
        <ZebraFields values={values} errors={errors} onChange={(next) => (setErrors((e) => pruneErrors(e, values, next)), setValues(next))} disabled={busy} />
        <div className="grid gap-4 border-t border-line pt-5 sm:grid-cols-[1fr_10rem]">
          <ImagePicker file={file} onChange={setFile} disabled={busy} label="Reference photograph (optional)" />
          <Select label="Flank" value={side} onChange={(e) => setSide(e.target.value)} disabled={busy || !file}>
            {FLANK_SIDES.map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </Select>
        </div>
        {formError && (
          <p role="alert" className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {formError}
          </p>
        )}
      </form>
    </Dialog>
  )
}
