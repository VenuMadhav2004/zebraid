// Field rules mirror backend app/schemas/zebra.py (ZebraCreate / ZebraUpdate).
export const CODE_PATTERN = /^[A-Za-z0-9_.-]+$/
export const LIMITS = { code: 40, name: 120, species: 80, sex: 20 }

// Suggestions only; species is free text in the backend.
export const SPECIES_SUGGESTIONS = ['Equus quagga', 'Equus grevyi', 'Equus zebra']
export const SEX_OPTIONS = [
  ['', 'Not recorded'],
  ['female', 'Female'],
  ['male', 'Male'],
  ['unknown', 'Unknown'],
]

export function validateZebra(values, { requireCode = true } = {}) {
  const errors = {}
  const code = values.code?.trim() ?? ''
  if (requireCode) {
    if (!code) errors.code = 'Required'
    else if (code.length > LIMITS.code) errors.code = `At most ${LIMITS.code} characters`
    else if (!CODE_PATTERN.test(code)) errors.code = 'Letters, digits, dot, dash and underscore only'
  }
  for (const f of ['name', 'species', 'sex']) {
    if ((values[f]?.trim().length ?? 0) > LIMITS[f]) errors[f] = `At most ${LIMITS[f]} characters`
  }
  return errors
}

/** '' -> null so optional text columns are cleared rather than set to an empty string. */
export const blankToNull = (v) => {
  const t = typeof v === 'string' ? v.trim() : v
  return t === '' || t === undefined ? null : t
}

/** Map an ApiError onto form fields where possible. */
export function fieldErrorsFrom(err) {
  const out = {}
  if (err?.code === 'zebra_code_exists') out.code = 'This code is already registered'
  if (err?.code === 'validation_error' && Array.isArray(err.details)) {
    for (const d of err.details) {
      const field = d.loc?.[d.loc.length - 1]
      if (typeof field === 'string') out[field] = d.msg
    }
  }
  return out
}

/** Drop errors for fields whose value changed (used as the user types). */
export function pruneErrors(errors, prev, next) {
  const out = { ...errors }
  for (const k of Object.keys(next)) if (prev[k] !== next[k]) delete out[k]
  return out
}
