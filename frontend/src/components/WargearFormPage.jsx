import { useState } from 'react'
import { createWargear, updateWargear } from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'

function buildEmptyForm(defaultModelId) {
  return {
    name: '',
    model_id: defaultModelId ? String(defaultModelId) : '',
    description: '',
    ability_ids: [],
  }
}

function formFromWargear(item) {
  return {
    name: item.name,
    model_id: String(item.model_id),
    description: item.description ?? '',
    ability_ids: item.ability_ids,
  }
}

function toPayload(form) {
  return {
    name: form.name,
    model_id: Number(form.model_id),
    description: form.description || null,
    ability_ids: form.ability_ids,
  }
}

function WargearFormPage({ editingWargear, defaultModelId, wargearAbilities, onSaved, onCancel }) {
  const [form, setForm] = useState(
    editingWargear ? formFromWargear(editingWargear) : buildEmptyForm(defaultModelId),
  )
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingWargear) {
        await updateWargear(editingWargear.id, toPayload(form))
      } else {
        await createWargear(toPayload(form))
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingWargear ? `Edit Wargear #${editingWargear.id}` : 'Add Wargear'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={form.name} onChange={handleChange('name')} required />
        </Field>
        <Field label="Description (optional)">
          <input value={form.description} onChange={handleChange('description')} />
        </Field>
        <div className="field">
          Wargear Abilities
          <MultiSelect
            options={wargearAbilities}
            value={form.ability_ids}
            onChange={(ability_ids) => setForm({ ...form, ability_ids })}
          />
        </div>
        <button type="submit">{editingWargear ? 'Save Changes' : 'Add Wargear'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default WargearFormPage
