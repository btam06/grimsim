import { useState } from 'react'
import { createWargear } from '../api'
import Field from './Field'

const EMPTY_FORM = {
  name: '',
  description: '',
  ability_ids: [],
}

function AddWargearForm({ modelId, wargearAbilities, onAdded }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const toggleAbility = (id) => {
    setForm({
      ...form,
      ability_ids: form.ability_ids.includes(id)
        ? form.ability_ids.filter((x) => x !== id)
        : [...form.ability_ids, id],
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createWargear({
        name: form.name,
        model_id: modelId,
        description: form.description || null,
        ability_ids: form.ability_ids,
      })
      setForm(EMPTY_FORM)
      onAdded()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      {error && <p className="error">{error}</p>}
      <Field label="Wargear Name">
        <input value={form.name} onChange={handleChange('name')} required />
      </Field>
      <Field label="Description (optional)">
        <input value={form.description} onChange={handleChange('description')} />
      </Field>
      <div className="checkbox-group">
        Abilities
        <div className="checkbox-grid">
          {wargearAbilities.map((a) => (
            <label key={a.id} className="checkbox-field">
              <input
                type="checkbox"
                checked={form.ability_ids.includes(a.id)}
                onChange={() => toggleAbility(a.id)}
              />
              {a.name}
            </label>
          ))}
        </div>
      </div>
      <button type="submit">Add Wargear</button>
    </form>
  )
}

export default AddWargearForm
