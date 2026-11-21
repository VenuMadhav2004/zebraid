import { useId } from 'react'
import { SEX_OPTIONS, SPECIES_SUGGESTIONS } from '../../lib/zebraForm.js'
import { ZEBRA_STATUSES } from '../../services/zebraid.js'
import { Input, Select, Textarea } from '../ui/index.js'

/** Shared metadata fields for register + edit. `values`/`errors` are plain objects. */
export function ZebraFields({ values, errors, onChange, disabled, showCode = true }) {
  const listId = useId()
  const set = (field) => (e) => onChange({ ...values, [field]: e.target.value })
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {showCode && (
        <Input
          label="Zebra code"
          required
          value={values.code}
          onChange={set('code')}
          error={errors.code}
          hint="Unique ID, e.g. ZB-0001. Cannot be changed later."
          placeholder="ZB-0001"
          maxLength={40}
          autoComplete="off"
          disabled={disabled}
          autoFocus
        />
      )}
      <Input label="Name" value={values.name} onChange={set('name')} error={errors.name} placeholder="Optional" maxLength={120} disabled={disabled} />
      <div>
        <Input
          label="Species"
          value={values.species}
          onChange={set('species')}
          error={errors.species}
          placeholder="Leave empty if not confirmed"
          maxLength={80}
          list={listId}
          disabled={disabled}
        />
        <datalist id={listId}>
          {SPECIES_SUGGESTIONS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
      <Select label="Sex" value={values.sex} onChange={set('sex')} error={errors.sex} disabled={disabled}>
        {SEX_OPTIONS.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </Select>
      <Select label="Status" value={values.status} onChange={set('status')} disabled={disabled}>
        {ZEBRA_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s[0].toUpperCase() + s.slice(1)}
          </option>
        ))}
      </Select>
      <Textarea
        className="sm:col-span-2"
        label="Notes"
        value={values.notes}
        onChange={set('notes')}
        rows={3}
        placeholder="Distinguishing marks, field remarks"
        disabled={disabled}
      />
    </div>
  )
}
