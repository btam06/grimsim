import { useState } from 'react'
import { createModel, deleteWeapon, updateModel } from '../api'
import { skillLabel } from '../weaponDisplay'
import AddWargearForm from './AddWargearForm'
import Field from './Field'
import MultiSelect from './MultiSelect'
import Select from './Select'

function buildEmptyForm() {
  return {
    name: '',
    faction_id: '',
    save: '',
    toughness: '',
    oc: '',
    movement: '',
    wounds: '',
    leadership: '',
    invulnerable: '',
    feel_no_pain: '',
    is_support: false,
    is_leader: false,
    ability_ids: [],
    wargear_ids: [],
    keyword_ids: [],
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
    leadership: String(model.leadership),
    invulnerable: model.invulnerable === null ? '' : String(model.invulnerable),
    feel_no_pain: model.feel_no_pain === null ? '' : String(model.feel_no_pain),
    is_support: model.is_support,
    is_leader: model.is_leader,
    ability_ids: model.ability_ids,
    wargear_ids: [],
    keyword_ids: model.keyword_ids,
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
    leadership: Number(form.leadership),
    invulnerable: form.invulnerable === '' ? null : Number(form.invulnerable),
    feel_no_pain: form.feel_no_pain === '' ? null : Number(form.feel_no_pain),
    is_support: form.is_support,
    is_leader: form.is_leader,
    ability_ids: form.ability_ids,
    wargear_ids: form.wargear_ids,
    keyword_ids: form.keyword_ids,
  }
}

function ModelFormPage({
  editingModel,
  factions,
  abilities,
  keywords,
  weapons,
  wargear,
  wargearAbilities,
  onSaved,
  onSavedStay,
  onCancel,
  onInventoryChanged,
  onAddWeapon,
  onEditWeapon,
}) {
  const [form, setForm] = useState(editingModel ? formFromModel(editingModel) : buildEmptyForm())
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const save = () =>
    editingModel ? updateModel(editingModel.id, toPayload(form)) : createModel(toPayload(form))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!form.faction_id) {
      setError('Faction is required')
      return
    }
    try {
      await save()
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleSaveAndStay = async () => {
    setError(null)
    if (!form.faction_id) {
      setError('Faction is required')
      return
    }
    try {
      const result = await save()
      onSavedStay(result)
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDeleteWeapon = async (id) => {
    setError(null)
    try {
      await deleteWeapon(id)
      onInventoryChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const wargearOptions = wargear.map((g) => ({
    id: g.id,
    name: `${g.name} (currently on model #${g.model_id})`,
  }))
  const weaponsOnThisModel = editingModel
    ? weapons.filter((w) => w.model_id === editingModel.id)
    : []

  return (
    <section>
      <h2>{editingModel ? `Edit Model #${editingModel.id}` : 'Add Model'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={form.name} onChange={handleChange('name')} required />
        </Field>
        <Field label="Faction">
          <Select
            options={factions}
            value={form.faction_id}
            onChange={(faction_id) => setForm({ ...form, faction_id })}
            placeholder="Select faction"
          />
        </Field>
        <Field label="Movement">
          <input type="number" value={form.movement} onChange={handleChange('movement')} required />
        </Field>
        <Field label="Toughness">
          <input
            type="number"
            value={form.toughness}
            onChange={handleChange('toughness')}
            required
          />
        </Field>
        <Field label="OC">
          <input type="number" value={form.oc} onChange={handleChange('oc')} required />
        </Field>
        <Field label="Wounds">
          <input type="number" value={form.wounds} onChange={handleChange('wounds')} required />
        </Field>
        <Field label="Save">
          <input type="number" value={form.save} onChange={handleChange('save')} required />
        </Field>
        <Field label="Leadership">
          <input
            type="number"
            value={form.leadership}
            onChange={handleChange('leadership')}
            required
          />
        </Field>
        <Field label="Invulnerable (optional)">
          <input type="number" value={form.invulnerable} onChange={handleChange('invulnerable')} />
        </Field>
        <Field label="Feel No Pain (optional)">
          <input type="number" value={form.feel_no_pain} onChange={handleChange('feel_no_pain')} />
        </Field>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={form.is_support}
            onChange={(e) => setForm({ ...form, is_support: e.target.checked })}
          />
          Support
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={form.is_leader}
            onChange={(e) => setForm({ ...form, is_leader: e.target.checked })}
          />
          Leader
        </label>
        <div className="field">
          Keywords
          <MultiSelect
            options={keywords}
            value={form.keyword_ids}
            onChange={(keyword_ids) => setForm({ ...form, keyword_ids })}
          />
        </div>
        <label className="field">
          Datasheet Abilities
          <MultiSelect
            options={abilities}
            value={form.ability_ids}
            onChange={(ability_ids) => setForm({ ...form, ability_ids })}
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
        <button type="button" onClick={handleSaveAndStay}>
          {editingModel ? 'Save & Continue Editing' : 'Add & Continue Editing'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
      {editingModel && (
        <>
          <h3>Weapons</h3>
          <button type="button" onClick={() => onAddWeapon(editingModel.id)}>
            + Add Weapon
          </button>
          {weaponsOnThisModel.length > 0 && (
            <ul>
              {weaponsOnThisModel.map((w) => (
                <li key={w.id}>
                  {w.name} —{w.range !== null ? ` R${w.range}"` : ''} A{w.attacks} S{w.strength} AP
                  {w.ap} D{w.damage} {skillLabel(w.weapon_type)}
                  {w.skill}+
                  <button type="button" onClick={() => onEditWeapon(w)}>
                    Edit
                  </button>
                  <button type="button" onClick={() => handleDeleteWeapon(w.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
          <AddWargearForm
            modelId={editingModel.id}
            wargearAbilities={wargearAbilities}
            onAdded={onInventoryChanged}
          />
        </>
      )}
    </section>
  )
}

export default ModelFormPage
