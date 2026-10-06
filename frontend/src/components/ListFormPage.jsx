import { useState } from 'react'
import { createList, deleteUnit, updateList } from '../api'
import AddUnitForm from './AddUnitForm'
import MultiSelect from './MultiSelect'

function buildEmptyForm() {
  return {
    name: '',
    points_limit: '2000',
    faction_id: '',
    detachment_id: '',
    unit_ids: [],
  }
}

function formFromList(list) {
  return {
    name: list.name,
    points_limit: String(list.points_limit),
    faction_id: String(list.faction_id),
    detachment_id: String(list.detachment_id),
    unit_ids: [],
  }
}

function toPayload(form) {
  return {
    name: form.name,
    points_limit: Number(form.points_limit),
    faction_id: Number(form.faction_id),
    detachment_id: Number(form.detachment_id),
    unit_ids: form.unit_ids,
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
  onSaved,
  onCancel,
  onUnitsChanged,
}) {
  const [form, setForm] = useState(editingList ? formFromList(editingList) : buildEmptyForm())
  const [error, setError] = useState(null)

  const detachmentOptionsForFaction = detachments.filter(
    (d) => String(d.faction_id) === form.faction_id
  )
  const unitOptions = units.map((u) => ({
    id: u.id,
    name: `${u.name} (${u.list_id === null ? 'unassigned' : `currently in list #${u.list_id}`})`,
  }))
  const unitsInThisList = editingList ? units.filter((u) => u.list_id === editingList.id) : []

  const handleFactionChange = (e) => {
    setForm({ ...form, faction_id: e.target.value, detachment_id: '' })
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
        <input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <select
          value={form.points_limit}
          onChange={(e) => setForm({ ...form, points_limit: e.target.value })}
          required
        >
            <option value="2000">2000 points</option>
          <option value="1000">1000 points</option>
        </select>
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
        <select
          value={form.detachment_id}
          onChange={(e) => setForm({ ...form, detachment_id: e.target.value })}
          disabled={!form.faction_id}
          required
        >
          <option value="" disabled>
            Select detachment
          </option>
          {detachmentOptionsForFaction.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <label className="field">
          Existing Units (reassigns them to this list)
          <MultiSelect
            options={unitOptions}
            value={form.unit_ids}
            onChange={(unit_ids) => setForm({ ...form, unit_ids })}
          />
        </label>
        <button type="submit">{editingList ? 'Save Changes' : 'Add List'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>

      {editingList && (
        <>
          {unitsInThisList.length > 0 && (
            <ul>
              {unitsInThisList.map((u) => (
                <li key={u.id}>
                  {u.name} — {u.points}pts
                  {u.unit_models.length > 0 && (
                    <ul>
                      {u.unit_models.map((m) => {
                        {m.weapon_ids.length > 0 && ` — Weapons: ${m.weapon_ids.map(weaponName).join(', ')}`}
                        {m.wargear_ids.length > 0 &&
                          ` — Wargear: ${m.wargear_ids.map(wargearName).join(', ')}`}
                      })}
                    </ul>
                  )}
                  <button type="button" onClick={() => handleDeleteUnit(u.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
          <AddUnitForm
            listId={editingList.id}
            models={models}
            weapons={weapons}
            wargear={wargear}
            onAdded={onUnitsChanged}
          />
        </>
      )}
    </section>
  )
}

export default ListFormPage
