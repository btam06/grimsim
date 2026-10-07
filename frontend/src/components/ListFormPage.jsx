import { useState } from 'react'
import { createList, deleteUnit, updateList } from '../api'
import Field from './Field'

function buildEmptyForm() {
  return {
    name: '',
    points_limit: '2000',
    faction_id: '',
    detachment_ids: [],
  }
}

function formFromList(list) {
  return {
    name: list.name,
    points_limit: String(list.points_limit),
    faction_id: String(list.faction_id),
    detachment_ids: list.detachment_ids,
  }
}

function toPayload(form) {
  return {
    name: form.name,
    points_limit: Number(form.points_limit),
    faction_id: Number(form.faction_id),
    detachment_ids: form.detachment_ids,
  }
}

function ListFormPage({
  editingList,
  factions,
  detachments,
  units,
  models,
  weapons,
  wargear,
  factionUnits,
  onSaved,
  onCancel,
  onUnitsChanged,
  onAddUnit,
  onEditUnit,
}) {
  const [form, setForm] = useState(editingList ? formFromList(editingList) : buildEmptyForm())
  const [error, setError] = useState(null)

  const detachmentOptionsForFaction = detachments.filter(
    (d) => String(d.faction_id) === form.faction_id
  )
  const unitsInThisList = editingList ? units.filter((u) => u.list_id === editingList.id) : []
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const factionUnitName = (id) => factionUnits.find((fu) => fu.id === id)?.name ?? `#${id}`

  const handleFactionChange = (e) => {
    setForm({ ...form, faction_id: e.target.value, detachment_ids: [] })
  }

  const toggleDetachment = (id) => {
    setForm({
      ...form,
      detachment_ids: form.detachment_ids.includes(id)
        ? form.detachment_ids.filter((d) => d !== id)
        : [...form.detachment_ids, id],
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingList) {
        await updateList(editingList.id, toPayload(form))
      } else {
        await createList(toPayload(form))
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDeleteUnit = async (id) => {
    setError(null)
    try {
      await deleteUnit(id)
      onUnitsChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingList ? `Edit List #${editingList.id}` : 'Add List'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </Field>
        <Field label="Points Limit">
          <select
            value={form.points_limit}
            onChange={(e) => setForm({ ...form, points_limit: e.target.value })}
            required
          >
            <option value="2000">2000 points</option>
            <option value="1000">1000 points</option>
          </select>
        </Field>
        <Field label="Faction">
          <select value={form.faction_id} onChange={handleFactionChange} required>
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
        <div className="checkbox-group">
          Detachments
          {detachmentOptionsForFaction.length === 0 && (
            <p className="hint">Select a faction to see its detachments</p>
          )}
          {detachmentOptionsForFaction.map((d) => (
            <label key={d.id} className="checkbox-field">
              <input
                type="checkbox"
                checked={form.detachment_ids.includes(d.id)}
                onChange={() => toggleDetachment(d.id)}
              />
              {d.name}
            </label>
          ))}
        </div>
        <button type="submit">{editingList ? 'Save Changes' : 'Add List'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>

      {editingList && (
        <>
          <h3>Units</h3>
          <button type="button" onClick={() => onAddUnit(editingList.id)}>
            + Add Unit
          </button>
          {unitsInThisList.length > 0 && (
            <ul>
              {unitsInThisList.map((u) => (
                <li key={u.id}>
                  {factionUnitName(u.faction_unit_id)} — {u.points}pts
                  {u.unit_models.length > 0 && (
                    <ul>
                      {u.unit_models.map((m) => (
                        <li key={m.id}>
                          {modelName(m.model_id)}
                          {m.weapon_ids.length > 0 &&
                            ` — Weapons: ${m.weapon_ids.map(weaponName).join(', ')}`}
                          {m.wargear_ids.length > 0 &&
                            ` — Wargear: ${m.wargear_ids.map(wargearName).join(', ')}`}
                        </li>
                      ))}
                    </ul>
                  )}
                  <button type="button" onClick={() => onEditUnit(u)}>
                    Edit
                  </button>
                  <button type="button" onClick={() => handleDeleteUnit(u.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}

export default ListFormPage
