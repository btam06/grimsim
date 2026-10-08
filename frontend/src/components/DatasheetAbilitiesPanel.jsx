import { useEffect, useState } from 'react'
import { createDatasheetAbility, listConditions, listDatasheetAbilities, listEffects } from '../api'
import Field from './Field'

function DatasheetAbilitiesPanel() {
  const [abilities, setAbilities] = useState([])
  const [conditions, setConditions] = useState([])
  const [effects, setEffects] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [conditionIds, setConditionIds] = useState([])
  const [effectIds, setEffectIds] = useState([])
  const [error, setError] = useState(null)

  const refresh = () =>
    listDatasheetAbilities().then(setAbilities).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listConditions().then(setConditions).catch((err) => setError(err.message))
    listEffects().then(setEffects).catch((err) => setError(err.message))
  }, [])

  const conditionName = (id) => conditions.find((c) => c.id === id)?.name ?? `#${id}`
  const effectName = (id) => effects.find((e) => e.id === id)?.name ?? `#${id}`

  const toggleId = (list, setList, id) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createDatasheetAbility({
        name,
        description: description || null,
        condition_ids: conditionIds,
        effect_ids: effectIds,
      })
      setName('')
      setDescription('')
      setConditionIds([])
      setEffectIds([])
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Datasheet Abilities</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="checkbox-group">
          Conditions
          <div className="checkbox-grid">
            {conditions.map((c) => (
              <label key={c.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={conditionIds.includes(c.id)}
                  onChange={() => toggleId(conditionIds, setConditionIds, c.id)}
                />
                {c.name}
              </label>
            ))}
          </div>
        </div>
        <div className="checkbox-group">
          Effects
          <div className="checkbox-grid">
            {effects.map((e) => (
              <label key={e.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={effectIds.includes(e.id)}
                  onChange={() => toggleId(effectIds, setEffectIds, e.id)}
                />
                {e.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit">Add</button>
      </form>
      <ul>
        {abilities.map((item) => (
          <li key={item.id}>
            #{item.id} {item.name}
            {item.description ? ` — ${item.description}` : ''}
            {item.condition_ids.length > 0 &&
              ` — Conditions: ${item.condition_ids.map(conditionName).join(', ')}`}
            {item.effect_ids.length > 0 &&
              ` — Effects: ${item.effect_ids.map(effectName).join(', ')}`}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default DatasheetAbilitiesPanel
