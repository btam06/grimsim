import { useState } from 'react'
import { createUnit } from '../api'
import MultiSelect from './MultiSelect'

const EMPTY_SLOT = {
  model_id: '',
  weapon_ids: [],
  wargear_ids: [],
}

function AddUnitForm({ listId, models, weapons, wargear, onAdded }) {
  const [name, setName] = useState('')
  const [points, setPoints] = useState('')
  const [slot, setSlot] = useState(EMPTY_SLOT)
  const [slots, setSlots] = useState([])
  const [error, setError] = useState(null)

  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`

  const weaponOptionsForSlot = weapons.filter((w) => String(w.model_id) === slot.model_id)
  const wargearOptionsForSlot = wargear.filter((g) => String(g.model_id) === slot.model_id)

  const addSlot = () => {
    if (!slot.model_id) return
    setSlots([...slots, slot])
    setSlot(EMPTY_SLOT)
  }

  const removeSlot = (index) => setSlots(slots.filter((_, i) => i !== index))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createUnit({
        name,
        points: Number(points),
        list_id: listId ?? null,
        unit_models: slots.map((s) => ({
          model_id: Number(s.model_id),
          weapon_ids: s.weapon_ids,
          wargear_ids: s.wargear_ids,
        })),
      })
      setName('')
      setPoints('')
      setSlots([])
      onAdded()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      {error && <p className="error">{error}</p>}
      <input
        placeholder="Unit Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <input
        placeholder="Points"
        type="number"
        value={points}
        onChange={(e) => setPoints(e.target.value)}
        required
      />

      {slots.length > 0 && (
        <ul>
          {slots.map((s, i) => (
            <li key={i}>
              {modelName(Number(s.model_id))}
              {s.weapon_ids.length > 0 && ` — ${s.weapon_ids.map(weaponName).join(', ')}`}
              {s.wargear_ids.length > 0 && ` — ${s.wargear_ids.map(wargearName).join(', ')}`}
              <button type="button" onClick={() => removeSlot(i)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <select
        value={slot.model_id}
        onChange={(e) => setSlot({ model_id: e.target.value, weapon_ids: [], wargear_ids: [] })}
      >
        <option value="" disabled>
          Select model
        </option>
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
      <label className="field">
        Weapons
        <MultiSelect
          options={weaponOptionsForSlot}
          value={slot.weapon_ids}
          onChange={(weapon_ids) => setSlot({ ...slot, weapon_ids })}
        />
      </label>
      <label className="field">
        Wargear
        <MultiSelect
          options={wargearOptionsForSlot}
          value={slot.wargear_ids}
          onChange={(wargear_ids) => setSlot({ ...slot, wargear_ids })}
        />
      </label>
      <button type="button" disabled={!slot.model_id} onClick={addSlot}>
        Add Model to Unit
      </button>

      <button type="submit">Add Unit</button>
    </form>
  )
}

export default AddUnitForm
