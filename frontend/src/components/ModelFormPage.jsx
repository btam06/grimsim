import { useState } from 'react'
import { createModel, updateModel } from '../api'
import AddWargearForm from './AddWargearForm'
import AddWeaponForm from './AddWeaponForm'
import MultiSelect from './MultiSelect'

function buildEmptyForm() {
  return {
    name: '',
    faction_id: '',
    save: '',
    toughness: '',
    oc: '',
    movement: '',
    wounds: '',
    invulnerable: '',
    feel_no_pain: '',
    ability_ids: [],
    weapon_ids: [],
    wargear_ids: [],
  }
}

function formFromModel(model) {
  return {
    name: model.name,
    faction_id: String(model.faction_id),
    save: String(model.save),
    toughness: String(model.toughness),
    oc: String(model.oc),
    movement: String(model.movement),
    wounds: String(model.wounds),
    invulnerable: model.invulnerable === null ? '' : String(model.invulnerable),
    feel_no_pain: model.feel_no_pain === null ? '' : String(model.feel_no_pain),
    ability_ids: model.ability_ids,
    weapon_ids: [],
    wargear_ids: [],
  }
}

function toPayload(form) {
  return {
    name: form.name,
    faction_id: Number(form.faction_id),
    save: Number(form.save),
    toughness: Number(form.toughness),
    oc: Number(form.oc),
    movement: Number(form.movement),
    wounds: Number(form.wounds),
    invulnerable: form.invulnerable === '' ? null : Number(form.invulnerable),
    feel_no_pain: form.feel_no_pain === '' ? null : Number(form.feel_no_pain),
    ability_ids: form.ability_ids,
    weapon_ids: form.weapon_ids,
    wargear_ids: form.wargear_ids,
  }
}

function ModelFormPage({
  editingModel,
  factions,
  abilities,
  weapons,
  weaponAbilities,
  wargear,
  onSaved,
  onCancel,
  onInventoryChanged,
}) {
  const [form, setForm] = useState(editingModel ? formFromModel(editingModel) : buildEmptyForm())
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingModel) {
        await updateModel(editingModel.id, toPayload(form))
      } else {
        await createModel(toPayload(form))
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  const weaponOptions = weapons.map((w) => ({
    id: w.id,
    name: `${w.name} (currently on model #${w.model_id})`,
  }))
  const wargearOptions = wargear.map((g) => ({
    id: g.id,
    name: `${g.name} (currently on model #${g.model_id})`,
  }))

  return (
    <section>
      <h2>{editingModel ? `Edit Model #${editingModel.id}` : 'Add Model'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <input placeholder="Name" value={form.name} onChange={handleChange('name')} required />
        <select value={form.faction_id} onChange={handleChange('faction_id')} required>
          <option value="" disabled>
            Select faction
          </option>
          {factions.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
        <input
          placeholder="Movement"
          type="number"
          value={form.movement}
          onChange={handleChange('movement')}
          required
        />
        <input
          placeholder="Toughness"
          type="number"
          value={form.toughness}
          onChange={handleChange('toughness')}
          required
        />
        <input placeholder="OC" type="number" value={form.oc} onChange={handleChange('oc')} required />
        <input
          placeholder="Wounds"
          type="number"
          value={form.wounds}
          onChange={handleChange('wounds')}
          required
        />
        <input
          placeholder="Save"
          type="number"
          value={form.save}
          onChange={handleChange('save')}
          required
        />
        <input
          placeholder="Invulnerable (optional)"
          type="number"
          value={form.invulnerable}
          onChange={handleChange('invulnerable')}
        />
        <input
          placeholder="Feel No Pain (optional)"
          type="number"
          value={form.feel_no_pain}
          onChange={handleChange('feel_no_pain')}
        />
        <label className="field">
          Datasheet Abilities
          <MultiSelect
            options={abilities}
            value={form.ability_ids}
            onChange={(ability_ids) => setForm({ ...form, ability_ids })}
          />
        </label>
        <label className="field">
          Existing Weapons (reassigns additional weapons to this model)
          <MultiSelect
            options={weaponOptions}
            value={form.weapon_ids}
            onChange={(weapon_ids) => setForm({ ...form, weapon_ids })}
          />
        </label>
        <label className="field">
          Existing Wargear (reassigns additional wargear to this model)
          <MultiSelect
            options={wargearOptions}
            value={form.wargear_ids}
            onChange={(wargear_ids) => setForm({ ...form, wargear_ids })}
          />
        </label>
        <button type="submit">{editingModel ? 'Save Changes' : 'Add Model'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
      {editingModel && (
        <>
          <AddWeaponForm
            modelId={editingModel.id}
            weaponAbilities={weaponAbilities}
            onAdded={onInventoryChanged}
          />
          <AddWargearForm modelId={editingModel.id} onAdded={onInventoryChanged} />
        </>
      )}
    </section>
  )
}

export default ModelFormPage
