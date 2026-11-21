import { useState } from 'react'
import { useToast } from '../../hooks/toastContext.js'
import { fromLocalInput, toLocalInput, validateSighting } from '../../lib/sightingForm.js'
import { imagesApi, sightingsApi } from '../../services/zebraid.js'
import { Button, Dialog, Input, Textarea } from '../ui/index.js'
import { ImagePicker } from '../zebras/ImagePicker.jsx'
import { ZebraPicker } from './ZebraPicker.jsx'

const FORM_ID = 'sighting-form'
const OBSERVER_KEY = 'zebraid.observer'
const TEXT_FIELDS = ['location_name', 'observer', 'notes']

const remembered = () => {
  try {
    return localStorage.getItem(OBSERVER_KEY) || ''
  } catch {
    return ''
  }
}

const trimOrNull = (v) => (v?.trim() ? v.trim() : null)

/**
 * Record (sighting = undefined) or edit a sighting.
 * Create: optional photo is uploaded as a `query` image first; identical bytes already
 * stored reuse the existing image (409 duplicate_image). If the sighting then fails,
 * a newly uploaded image is deleted again.
 * Edit: PATCH only changed fields. The photo cannot be changed after creation (backend schema).
 */
export default function SightingFormDialog({ sighting, zebra: initialZebra, onClose, onSaved }) {
  const { toast } = useToast()
  const editing = Boolean(sighting)
  const [values, setValues] = useState(() => ({
    observed_at: editing ? toLocalInput(sighting.observed_at) : toLocalInput(new Date().toISOString()),
    location_name: sighting?.location_name ?? '',
    latitude: sighting?.latitude ?? '',
    longitude: sighting?.longitude ?? '',
    observer: editing ? (sighting.observer ?? '') : remembered(),
    notes: sighting?.notes ?? '',
  }))
  const [zebra, setZebra] = useState(initialZebra ?? null)
  const [file, setFile] = useState(null)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(null) // null | 'upload' | 'save'
  const [progress, setProgress] = useState(0)
  const [formError, setFormError] = useState(null)
  const [locating, setLocating] = useState(false)

  const set = (field) => (e) => {
    setValues((v) => ({ ...v, [field]: e.target.value }))
    setErrors((er) => ({ ...er, [field]: undefined }))
  }

  function locateMe() {
    if (!navigator.geolocation) return setFormError('This browser cannot provide a location.')
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setValues((v) => ({ ...v, latitude: pos.coords.latitude.toFixed(6), longitude: pos.coords.longitude.toFixed(6) }))
        setErrors((er) => ({ ...er, latitude: undefined, longitude: undefined }))
        setLocating(false)
      },
      (err) => {
        setFormError(`Location unavailable: ${err.message}`)
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15000 },
    )
  }

  async function submit(e) {
    e.preventDefault()
    setFormError(null)
    const { errors: found, coords } = validateSighting(values)
    setErrors(found)
    if (Object.keys(found).length) return

    const body = {
      observed_at: fromLocalInput(values.observed_at),
      zebra_id: zebra?.id ?? null,
      latitude: coords?.latitude ?? null,
      longitude: coords?.longitude ?? null,
      ...Object.fromEntries(TEXT_FIELDS.map((f) => [f, trimOrNull(values[f])])),
    }

    try {
      let saved
      if (editing) {
        const changes = {}
        // Minute precision in the form: only send observed_at if the user changed it (keeps stored seconds).
        if (values.observed_at !== toLocalInput(sighting.observed_at)) changes.observed_at = body.observed_at
        for (const k of ['zebra_id', ...TEXT_FIELDS]) {
          if (body[k] !== (sighting[k] ?? null)) changes[k] = body[k]
        }
        if (body.latitude !== sighting.latitude || body.longitude !== sighting.longitude) {
          changes.latitude = body.latitude // the backend requires both together
          changes.longitude = body.longitude
        }
        if (!Object.keys(changes).length) return onClose()
        setBusy('save')
        saved = await sightingsApi.update(sighting.id, changes)
      } else {
        let imageId = null
        let uploadedNew = false
        if (file) {
          setBusy('upload')
          try {
            const img = await imagesApi.upload(file, { kind: 'query', capturedAt: body.observed_at }, (ev) =>
              ev.total && setProgress(Math.round((ev.loaded / ev.total) * 100)),
            )
            imageId = img.id
            uploadedNew = true
          } catch (err) {
            if (err.code !== 'duplicate_image' || !err.details?.existing_image_id) throw err
            imageId = err.details.existing_image_id // same bytes already stored as a query image
          }
        }
        setBusy('save')
        try {
          saved = await sightingsApi.create({ ...body, image_asset_id: imageId })
        } catch (err) {
          if (uploadedNew) await imagesApi.remove(imageId).catch(() => {})
          throw err
        }
      }
      if (body.observer) {
        try {
          localStorage.setItem(OBSERVER_KEY, body.observer)
        } catch {
          /* ignore */
        }
      }
      toast({ title: editing ? 'Sighting updated' : 'Sighting recorded', description: zebra ? `Linked to ${zebra.code}.` : 'Unidentified individual.' })
      onSaved(saved)
    } catch (err) {
      if (err.code === 'validation_error' && Array.isArray(err.details)) {
        const mapped = {}
        for (const d of err.details) mapped[d.loc?.[d.loc.length - 1]] = d.msg
        setErrors(mapped)
      }
      setFormError(err.message)
      setBusy(null)
    }
  }

  const disabled = busy !== null

  return (
    <Dialog
      open
      size="lg"
      onClose={disabled ? undefined : onClose}
      title={editing ? 'Edit sighting' : 'Record sighting'}
      description={editing ? undefined : 'A field observation. Leave the zebra empty if the individual is not yet identified.'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={disabled}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={disabled}>
            {busy === 'upload' ? `Uploading ${progress}%` : busy === 'save' ? 'Saving…' : editing ? 'Save changes' : 'Record sighting'}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Observed at" type="datetime-local" required value={values.observed_at} onChange={set('observed_at')} error={errors.observed_at} disabled={disabled} />
          <ZebraPicker value={zebra} onChange={setZebra} disabled={disabled} hint="Only registered zebras can be linked." error={errors.zebra_id} />
        </div>

        <fieldset className="space-y-3 rounded-control border border-line p-4">
          <legend className="px-1 text-xs font-medium text-muted">Location</legend>
          <Input label="Place name" value={values.location_name} onChange={set('location_name')} error={errors.location_name} placeholder="e.g. Waterhole A" maxLength={200} disabled={disabled} />
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Input label="Latitude" inputMode="decimal" value={values.latitude} onChange={set('latitude')} error={errors.latitude} placeholder="-1.52" disabled={disabled} />
            <Input label="Longitude" inputMode="decimal" value={values.longitude} onChange={set('longitude')} error={errors.longitude} placeholder="35.14" disabled={disabled} />
            <Button variant="secondary" onClick={locateMe} loading={locating} disabled={disabled} className={errors.latitude || errors.longitude ? 'sm:mb-5' : ''}>
              Use my location
            </Button>
          </div>
          <p className="text-[0.6875rem] text-faint">Decimal degrees (WGS84). Locations of wildlife are sensitive: share exports carefully.</p>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Observer" value={values.observer} onChange={set('observer')} error={errors.observer} placeholder="Name or team" maxLength={120} disabled={disabled} />
          <div className="hidden sm:block" />
          <Textarea className="sm:col-span-2" label="Notes" value={values.notes} onChange={set('notes')} rows={3} placeholder="Behaviour, group size, condition…" disabled={disabled} />
        </div>

        {editing ? (
          <p className="text-xs text-faint">
            {sighting.image_asset_id ? 'The attached photograph cannot be replaced after recording.' : 'Photographs can only be attached when a sighting is recorded.'}
          </p>
        ) : (
          <ImagePicker file={file} onChange={setFile} disabled={disabled} label="Photograph (optional)" hint="JPEG, PNG or WebP · up to 10 MB · stored privately" />
        )}

        {formError && (
          <p role="alert" className="rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {formError}
          </p>
        )}
      </form>
    </Dialog>
  )
}
