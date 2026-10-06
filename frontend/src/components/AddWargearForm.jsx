import { useState } from 'react'
import { createWargear } from '../api'
import Field from './Field'

const EMPTY_FORM = {
  name: '',
  description: '',
}

function AddWargearForm({ modelId, onAdded }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createWargear({
        name: form.name,
        model_id: modelId,
        description: form.description || null,
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
      <button type="submit">Add Wargear</button>
    </form>
  )
}

export default AddWargearForm
