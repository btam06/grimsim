import { useEffect, useState } from 'react'
import { createFactionUnit, deleteFactionUnit, listFactionUnits, listFactions } from '../api'
import Field from './Field'

function FactionUnitsPanel() {
  const [factionUnits, setFactionUnits] = useState([])
  const [factions, setFactions] = useState([])
  const [name, setName] = useState('')
  const [factionId, setFactionId] = useState('')
  const [error, setError] = useState(null)

  const refresh = () =>
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listFactions().then(setFactions).catch((err) => setError(err.message))
  }, [])

  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createFactionUnit({ name, faction_id: Number(factionId) })
      setName('')
      setFactionId('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteFactionUnit(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Faction Units</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Faction">
          <select value={factionId} onChange={(e) => setFactionId(e.target.value)} required>
            <option value="" disabled>
              Select faction
            </option>
            {factions.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </Field>
        <button type="submit">Add Faction Unit</button>
      </form>
      <ul>
        {factionUnits.map((fu) => (
          <li key={fu.id}>
            {fu.name} ({factionName(fu.faction_id)})
            <button type="button" onClick={() => handleRemove(fu.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default FactionUnitsPanel
