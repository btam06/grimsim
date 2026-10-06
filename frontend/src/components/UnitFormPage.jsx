import { useState } from 'react'
import { createUnit, updateUnit } from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'

const EMPTY_SLOT = { model_id: '', weapon_ids: [], wargear_ids: [] }

function slotsFromUnit(unit) {
  return unit.unit_models.map((um) => ({
    model_id: String(um.model_id),
    weapon_ids: um.weapon_ids,
    wargear_ids: um.wargear_ids,
  }))
}

function UnitFormPage({
  editingUnit,
  defaultListId,
  models,
  weapons,
  wargear,
  lists,
  onSaved,
  onCancel,
}) {
  const [name, setName] = useState(editingUnit ? editingUnit.name : '')
  const [points, setPoints] = useState(editingUnit ? String(editingUnit.points) : '')
  const [listId, setListId] = useState(() => {
    if (editingUnit) return editingUnit.list_id === null ? '' : String(editingUnit.list_id)
    return defaultListId ? String(defaultListId) : ''
  })
  const [slot, setSlot] = useState(EMPTY_SLOT)
  const [quantity, setQuantity] = useState('1')
  const [slots, setSlots] = useState(editingUnit ? slotsFromUnit(editingUnit) : [])
  const [error, setError] = useState(null)

  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`

  const weaponOptionsForSlot = weapons.filter((w) => String(w.model_id) === slot.model_id)
  const wargearOptionsForSlot = wargear.filter((g) => String(g.model_id) === slot.model_id)

  const addSlot = () => {
    if (!slot.model_id) return
    const count = Math.max(1, Number(quantity) || 1)
    setSlots([...slots, ...Array.from({ length: count }, () => slot)])
    setSlot(EMPTY_SLOT)
    setQuantity('1')
  }

  const removeSlot = (index) => setSlots(slots.filter((_, i) => i !== index))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const payload = {
        name,
        points: Number(points),
        list_id: listId === '' ? null : Number(listId),
        unit_models: slots.map((s) => ({
          model_id: Number(s.model_id),
          weapon_ids: s.weapon_ids,
          wargear_ids: s.wargear_ids,
        })),
      }
      if (editingUnit) {
        await updateUnit(editingUnit.id, payload)
      } else {
        await createUnit(payload)
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingUnit ? `Edit Unit #${editingUnit.id}` : 'Add Unit'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Unit Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Points">
          <input type="number" value={points} onChange={(e) => setPoints(e.target.value)} required />
        </Field>
        <Field label="List">
          <select value={listId} onChange={(e) => setListId(e.target.value)}>
            <option value="">No list</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </Field>

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

        <Field label="Add model to unit">
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
        </Field>
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
        <Field label="Quantity">
          <input type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </Field>
        <button type="button" disabled={!slot.model_id} onClick={addSlot}>
          Add Model to Unit
        </button>

        <button type="submit">{editingUnit ? 'Save Changes' : 'Add Unit'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default UnitFormPage
