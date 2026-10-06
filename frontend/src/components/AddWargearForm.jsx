import { useState } from 'react'
import { createWargear } from '../api'

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
      <input placeholder="Wargear Name" value={form.name} onChange={handleChange('name')} required />
      <input
        placeholder="Description (optional)"
        value={form.description}
        onChange={handleChange('description')}
      />
      <button type="submit">Add Wargear</button>
    </form>
  )
}

export default AddWargearForm
