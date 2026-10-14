import { useState } from 'react'
import { attachDatasheetAbility, createDatasheetAbility, updateDatasheetAbility } from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'

function buildEmptyForm() {
  return {
    name: '',
    description: '',
    condition_ids: [],
    effect_ids: [],
  }
}

function formFromAbility(ability) {
  return {
    name: ability.name,
    description: ability.description ?? '',
    condition_ids: ability.condition_ids,
    effect_ids: ability.effect_ids,
  }
}

function toPayload(form) {
  return {
    name: form.name,
    description: form.description || null,
    condition_ids: form.condition_ids,
    effect_ids: form.effect_ids,
  }
}

function DatasheetAbilityFormPage({
  editingAbility,
  modelId,
  conditions,
  effects,
  onSaved,
  onCancel,
}) {
  const [form, setForm] = useState(
    editingAbility ? formFromAbility(editingAbility) : buildEmptyForm()
  )
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingAbility) {
        await updateDatasheetAbility(editingAbility.id, toPayload(form))
      } else {
        // A new ability is created and given to the model being edited.
        const created = await createDatasheetAbility(toPayload(form))
        await attachDatasheetAbility(modelId, created.id)
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>
        {editingAbility ? `Edit Datasheet Ability #${editingAbility.id}` : 'Add Datasheet Ability'}
      </h2>
      {editingAbility && (
        <p className="hint">Changes apply to every model with this ability.</p>
      )}
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={form.name} onChange={handleChange('name')} required />
        </Field>
        <Field label="Description (optional)">
          <input value={form.description} onChange={handleChange('description')} />
        </Field>
        <div className="field">
          Conditions
          <MultiSelect
            options={conditions}
            value={form.condition_ids}
            onChange={(condition_ids) => setForm({ ...form, condition_ids })}
          />
        </div>
        <div className="field">
          Effects
          <MultiSelect
            options={effects}
            value={form.effect_ids}
            onChange={(effect_ids) => setForm({ ...form, effect_ids })}
          />
        </div>
        <button type="submit">{editingAbility ? 'Save Changes' : 'Add Datasheet Ability'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default DatasheetAbilityFormPage
