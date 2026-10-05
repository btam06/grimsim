import { useEffect, useState } from 'react'
import { createUnit, listUnits } from '../api'

function UnitsPanel() {
  const [units, setUnits] = useState([])
  const [name, setName] = useState('')
  const [modelIds, setModelIds] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listUnits().then(setUnits).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const model_ids = modelIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
      await createUnit({ name, model_ids })
      setName('')
      setModelIds('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Units</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input
          placeholder="Model IDs (comma separated)"
          value={modelIds}
          onChange={(e) => setModelIds(e.target.value)}
        />
        <button type="submit">Add Unit</button>
      </form>
      <ul>
        {units.map((u) => (
          <li key={u.id}>
            #{u.id} {u.name} — models: {u.model_ids.join(', ') || 'none'}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default UnitsPanel
