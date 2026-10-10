import { useEffect, useState } from 'react'
import { createFactionAbility, deleteFactionAbility, listFactionAbilities, listFactions } from '../api'
import Field from './Field'
import Select from './Select'

function FactionAbilitiesPanel() {
  const [factionAbilities, setFactionAbilities] = useState([])
  const [factions, setFactions] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [factionId, setFactionId] = useState('')
  const [error, setError] = useState(null)

  const refresh = () =>
    listFactionAbilities().then(setFactionAbilities).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listFactions().then(setFactions).catch((err) => setError(err.message))
  }, [])

  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!factionId) {
      setError('Faction is required')
      return
    }
    try {
      await createFactionAbility({
        name,
        description: description || null,
        faction_id: Number(factionId),
      })
      setName('')
      setDescription('')
      setFactionId('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteFactionAbility(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Faction Abilities</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Faction">
          <Select options={factions} value={factionId} onChange={setFactionId} placeholder="Select faction" />
        </Field>
        <button type="submit">Add Faction Ability</button>
      </form>
      <ul>
        {factionAbilities.map((fa) => (
          <li key={fa.id}>
            {fa.name} ({factionName(fa.faction_id)})
            {fa.description ? ` — ${fa.description}` : ''}
            <button type="button" onClick={() => handleRemove(fa.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default FactionAbilitiesPanel
