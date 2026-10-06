import { useEffect, useState } from 'react'
import { createWeapon, listModels, listWeaponAbilities, listWeapons } from '../api'
import MultiSelect from './MultiSelect'

const EMPTY_FORM = {
  name: '',
  model_id: '',
  damage: '',
  range: '',
  strength: '',
  ap: '',
  attacks: '',
  ability_ids: [],
}

function toPayload(form) {
  return {
    name: form.name,
    model_id: Number(form.model_id),
    damage: form.damage,
    range: Number(form.range),
    strength: Number(form.strength),
    ap: Number(form.ap),
    attacks: Number(form.attacks),
    ability_ids: form.ability_ids,
  }
}

function WeaponsPanel() {
  const [weapons, setWeapons] = useState([])
  const [models, setModels] = useState([])
  const [abilities, setAbilities] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)

  const refresh = () => listWeapons().then(setWeapons).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listModels().then(setModels).catch((err) => setError(err.message))
    listWeaponAbilities()
      .then(setAbilities)
      .catch((err) => setError(err.message))
  }, [])

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createWeapon(toPayload(form))
      setForm(EMPTY_FORM)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`

  return (
    <section>
      <h2>Weapons</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <input placeholder="Name" value={form.name} onChange={handleChange('name')} required />
        <select value={form.model_id} onChange={handleChange('model_id')} required>
          <option value="" disabled>
            Select model
          </option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              #{m.id} {m.name}
            </option>
          ))}
        </select>
        <input
          placeholder="Damage (e.g. 1, 2, 1D3, 2D6)"
          type="text"
          pattern="[0-9](D[36])?"
          value={form.damage}
          onChange={handleChange('damage')}
          required
        />
        <input
          placeholder="Range"
          type="number"
          value={form.range}
          onChange={handleChange('range')}
          required
        />
        <input
          placeholder="Strength"
          type="number"
          value={form.strength}
          onChange={handleChange('strength')}
          required
        />
        <input
          placeholder="AP"
          type="number"
          value={form.ap}
          onChange={handleChange('ap')}
          required
        />
        <input
          placeholder="Attacks"
          type="number"
          value={form.attacks}
          onChange={handleChange('attacks')}
          required
        />
        <label className="field">
          Weapon Abilities
          <MultiSelect
            options={abilities}
            value={form.ability_ids}
            onChange={(ability_ids) => setForm({ ...form, ability_ids })}
          />
        </label>
        <button type="submit">Add Weapon</button>
      </form>
      <ul>
        {weapons.map((w) => (
          <li key={w.id}>
            #{w.id} {w.name} ({modelName(w.model_id)}) — R{w.range}" A{w.attacks} S{w.strength} AP
            {w.ap} D{w.damage}
            {w.ability_ids.length > 0 && ` — ${w.ability_ids.map(abilityName).join(', ')}`}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default WeaponsPanel
