import { useState } from 'react'
import { useToast } from '../../hooks/toastContext.js'
import { FLANK_SIDES, addReferencePhoto } from '../../services/zebraid.js'
import { Button, Dialog, Input, Select } from '../ui/index.js'
import { ImagePicker } from './ImagePicker.jsx'

const FORM_ID = 'add-photo-form'

export default function AddPhotoDialog({ zebra, onClose, onAdded }) {
  const { toast } = useToast()
  const [file, setFile] = useState(null)
  const [side, setSide] = useState('unknown')
  const [qualityNotes, setQualityNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!file) return setError('Choose a photograph')
    setBusy(true)
    setError(null)
    try {
      await addReferencePhoto(zebra.id, file, { side, qualityNotes }, (ev) => ev.total && setProgress(Math.round((ev.loaded / ev.total) * 100)))
      toast({ title: 'Photograph added', description: `Registered in the ${zebra.code} gallery.` })
      onAdded()
    } catch (err) {
      setError(err.code === 'duplicate_image' ? 'This exact photograph is already uploaded as a reference image.' : err.message)
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      title={`Add photograph to ${zebra.code}`}
      description="The image is stored privately and linked to this zebra's reference gallery."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={busy} disabled={!file}>
            {busy ? `Uploading ${progress}%` : 'Upload'}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
        <ImagePicker file={file} onChange={(f) => (setFile(f), setError(null))} disabled={busy} error={error} label="Photograph" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Flank" value={side} onChange={(e) => setSide(e.target.value)} disabled={busy}>
            {FLANK_SIDES.map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </Select>
          <Input label="Quality notes" value={qualityNotes} onChange={(e) => setQualityNotes(e.target.value)} placeholder="Optional" disabled={busy} />
        </div>
      </form>
    </Dialog>
  )
}
