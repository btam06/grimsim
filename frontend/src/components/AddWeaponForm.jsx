import { useState } from 'react'
import { createWeapon } from '../api'
import MultiSelect from './MultiSelect'

const EMPTY_FORM = {
  name: '',
  damage: '',
  range: '',
  strength: '',
  attacks: '',
  ability_ids: [],
}

function AddWeaponForm({ modelId, weaponAbilities, onAdded }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createWeapon({
        name: form.name,
        model_id: modelId,
        damage: Number(form.damage),
        range: Number(form.range),
        strength: Number(form.strength),
        attacks: Number(form.attacks),
        ability_ids: form.ability_ids,
      })
      setForm(EMPTY_FORM)
      onAdded()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="add-weapon-form" onSubmit={handleSubmit}>
      {error && <p className="error">{error}</p>}
      <input placeholder="Weapon Name" value={form.name} onChange={handleChange('name')} required />
      <input
        placeholder="Damage"
        type="number"
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
        placeholder="Attacks"
        type="number"
        value={form.attacks}
        onChange={handleChange('attacks')}
        required
      />
      <label className="field">
        Weapon Abilities
        <MultiSelect
          options={weaponAbilities}
          value={form.ability_ids}
          onChange={(ability_ids) => setForm({ ...form, ability_ids })}
        />
      </label>
      <button type="submit">Add Weapon</button>
    </form>
  )
}

export default AddWeaponForm
