import { useEffect, useState } from 'react'
import { createFaction, deleteFaction, listFactions } from '../api'
import Field from './Field'

function FactionsPanel() {
  const [factions, setFactions] = useState([])
  const [name, setName] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listFactions().then(setFactions).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createFaction({ name })
      setName('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteFaction(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Factions</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <button type="submit">Add Faction</button>
      </form>
      <ul>
        {factions.map((f) => (
          <li key={f.id}>
            {f.name}
            <button type="button" onClick={() => handleRemove(f.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default FactionsPanel
