import { useState } from 'react'
import { createList, createUnit, deleteUnit, updateList } from '../api'
import Field from './Field'
import Select from './Select'
import { CopyButton, DeleteButton, EditButton } from './IconButtons'

const POINTS_LIMIT_OPTIONS = [
  { id: '2000', name: '2000 points' },
  { id: '1000', name: '1000 points' },
]

function buildEmptyForm() {
  return {
    name: '',
    points_limit: '2000',
    faction_id: '',
    detachment_ids: [],
    user_id: '',
  }
}

function formFromList(list) {
  return {
    name: list.name,
    points_limit: String(list.points_limit),
    faction_id: String(list.faction_id),
    detachment_ids: list.detachment_ids,
    user_id: list.user_id === null ? '' : String(list.user_id),
  }
}

function toPayload(form) {
  return {
    name: form.name,
    points_limit: Number(form.points_limit),
    faction_id: Number(form.faction_id),
    detachment_ids: form.detachment_ids,
    user_id: form.user_id === '' ? null : Number(form.user_id),
  }
}

// Battlefield roles units are grouped under in the list builder, in order. A
// unit goes under the first one that every one of its models has - so a
// CHARACTER leading a unit sits with its bodyguard, not under Character.
const UNIT_CATEGORIES = [
  { label: 'Epic Hero', keyword: 'EPIC HERO' },
  { label: 'Character', keyword: 'CHARACTER' },
  { label: 'Battleline', keyword: 'BATTLELINE' },
  { label: 'Infantry', keyword: 'INFANTRY' },
  { label: 'Mounted', keyword: 'MOUNTED' },
  { label: 'Dedicated Transport', keyword: 'DEDICATED TRANSPORT' },
  { label: 'Monster', keyword: 'MONSTER' },
  { label: 'Vehicle', keyword: 'VEHICLE' },
]

function ListFormPage({
  editingList,
  users,
  factions,
  detachments,
  units,
  models,
  keywords,
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

  // Keyword names every model in the unit has.
  const sharedKeywords = (unit) => {
    const perModel = unit.unit_models.map(
      (um) =>
        new Set(
          (models.find((m) => m.id === um.model_id)?.keyword_ids ?? []).map(
            (id) => keywords.find((k) => k.id === id)?.name
          )
        )
    )
    if (perModel.length === 0) return new Set()
    return new Set([...perModel[0]].filter((name) => perModel.every((set) => set.has(name))))
  }
  const categoryOf = (unit) => {
    const shared = sharedKeywords(unit)
    return UNIT_CATEGORIES.find((c) => shared.has(c.keyword))?.label ?? 'Other'
  }
  // Only categories with units in them, in UNIT_CATEGORIES order, then Other.
  const unitGroups = [...UNIT_CATEGORIES.map((c) => c.label), 'Other']
    .map((label) => ({ label, units: unitsInThisList.filter((u) => categoryOf(u) === label) }))
    .filter((group) => group.units.length > 0)
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const factionUnitName = (id) => factionUnits.find((fu) => fu.id === id)?.name ?? `#${id}`

  const handleFactionChange = (faction_id) => {
    setForm({ ...form, faction_id, detachment_ids: [] })
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
    if (!form.faction_id) {
      setError('Faction is required')
      return
    }
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

  // Duplicates a unit - same datasheet, points and per-model loadout - into
  // this list, as a new unit that can then be edited on its own.
  const handleCopyUnit = async (unit) => {
    setError(null)
    try {
      await createUnit({
        faction_unit_id: unit.faction_unit_id,
        points: unit.points,
        list_id: unit.list_id,
        unit_models: unit.unit_models.map((m) => ({
          model_id: m.model_id,
          weapon_ids: m.weapon_ids,
          wargear_ids: m.wargear_ids,
        })),
      })
      onUnitsChanged()
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
        <Field label="Owner">
          <Select
            options={[{ id: '', name: 'No owner' }, ...users]}
            value={form.user_id}
            onChange={(user_id) => setForm({ ...form, user_id })}
          />
        </Field>
        <Field label="Points Limit">
          <Select
            options={POINTS_LIMIT_OPTIONS}
            value={form.points_limit}
            onChange={(points_limit) => setForm({ ...form, points_limit })}
          />
        </Field>
        <Field label="Faction">
          <Select
            options={factions}
            value={form.faction_id}
            onChange={handleFactionChange}
            placeholder="Select faction"
          />
        </Field>
        <div className="checkbox-group">
          Detachments
          {detachmentOptionsForFaction.length === 0 && (
            <p className="hint">Select a faction to see its detachments</p>
          )}
          <div className="checkbox-grid">
            {detachmentOptionsForFaction.map((d) => (
              <label key={d.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={form.detachment_ids.includes(d.id)}
                  onChange={() => toggleDetachment(d.id)}
                />
                {d.name} (DP {d.dp})
              </label>
            ))}
          </div>
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
          {unitGroups.map((group) => (
            <div key={group.label}>
              <h4>{group.label}</h4>
              <ul>
                {group.units.map((u) => (
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
                    <EditButton onClick={() => onEditUnit(u)} />
                    <CopyButton onClick={() => handleCopyUnit(u)} />
                    <DeleteButton onClick={() => handleDeleteUnit(u.id)} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </section>
  )
}

export default ListFormPage
