import { useState } from 'react'
import {
  createModel,
  deleteWargear,
  deleteWeapon,
  detachDatasheetAbility,
  updateModel,
} from '../api'
import { skillLabel } from '../weaponDisplay'
import Field from './Field'
import MultiSelect from './MultiSelect'
import Select from './Select'
import { DeleteButton, EditButton } from './IconButtons'

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
    base_size_id: '',
    ability_ids: [],
    keyword_ids: [],
    faction_ability_ids: [],
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
    base_size_id: model.base_size_id === null ? '' : String(model.base_size_id),
    ability_ids: model.ability_ids,
    keyword_ids: model.keyword_ids,
    faction_ability_ids: model.faction_ability_ids,
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
    base_size_id: form.base_size_id === '' ? null : Number(form.base_size_id),
    ability_ids: form.ability_ids,
    keyword_ids: form.keyword_ids,
    faction_ability_ids: form.faction_ability_ids,
  }
}

function ModelFormPage({
  editingModel,
  factions,
  abilities,
  keywords,
  baseSizes,
  factionAbilities,
  weapons,
  wargear,
  onSaved,
  onSavedStay,
  onCancel,
  onInventoryChanged,
  onAddWeapon,
  onEditWeapon,
  onAddWargear,
  onEditWargear,
  onAddAbility,
  onEditAbility,
}) {
  const [form, setForm] = useState(editingModel ? formFromModel(editingModel) : buildEmptyForm())
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // A faction with a single faction ability (e.g. Orks' Waaagh!) almost
  // always grants it to its models, so tick it when that faction is picked.
  // It can still be unticked.
  const selectFaction = (faction_id) => {
    const factionAbilityIds = factionAbilities
      .filter((a) => String(a.faction_id) === faction_id)
      .map((a) => a.id)
    const onlyAbilityId = factionAbilityIds.length === 1 ? factionAbilityIds[0] : null
    setForm({
      ...form,
      faction_id,
      faction_ability_ids:
        onlyAbilityId === null || form.faction_ability_ids.includes(onlyAbilityId)
          ? form.faction_ability_ids
          : [...form.faction_ability_ids, onlyAbilityId],
    })
  }

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

  // Datasheet abilities are shared, so this only takes the ability off this
  // model. It's kept in the form too, so saving the model doesn't re-add it.
  const handleRemoveAbility = async (id) => {
    setError(null)
    try {
      await detachDatasheetAbility(editingModel.id, id)
      setForm({ ...form, ability_ids: form.ability_ids.filter((x) => x !== id) })
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDeleteWargear = async (id) => {
    setError(null)
    try {
      await deleteWargear(id)
      onInventoryChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  // Offer the selected faction's abilities, plus any already attached (so one
  // from another faction stays visible and can be removed).
  const factionAbilityOptions = factionAbilities.filter(
    (a) => String(a.faction_id) === form.faction_id || form.faction_ability_ids.includes(a.id)
  )

  const weaponsOnThisModel = editingModel
    ? weapons.filter((w) => w.model_id === editingModel.id)
    : []
  const abilitiesOnThisModel = abilities.filter((a) => form.ability_ids.includes(a.id))
  const wargearOnThisModel = editingModel
    ? wargear.filter((g) => g.model_id === editingModel.id)
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
            onChange={selectFaction}
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
        <Field label="Base size">
          <Select
            options={[{ id: '', name: 'Not set' }, ...baseSizes]}
            value={form.base_size_id}
            onChange={(base_size_id) => setForm({ ...form, base_size_id })}
          />
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
          Faction Abilities
          <MultiSelect
            options={factionAbilityOptions}
            value={form.faction_ability_ids}
            onChange={(faction_ability_ids) => setForm({ ...form, faction_ability_ids })}
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
                  <EditButton onClick={() => onEditWeapon(w)} />
                  <DeleteButton onClick={() => handleDeleteWeapon(w.id)} />
                </li>
              ))}
            </ul>
          )}
          <h3>Wargear</h3>
          <button type="button" onClick={() => onAddWargear(editingModel.id)}>
            + Add Wargear
          </button>
          {wargearOnThisModel.length > 0 && (
            <ul>
              {wargearOnThisModel.map((g) => (
                <li key={g.id}>
                  {g.name}
                  {g.description ? ` — ${g.description}` : ''}
                  <EditButton onClick={() => onEditWargear(g)} />
                  <DeleteButton onClick={() => handleDeleteWargear(g.id)} />
                </li>
              ))}
            </ul>
          )}
          <h3>Datasheet Abilities</h3>
          <button type="button" onClick={onAddAbility}>
            + Add Datasheet Ability
          </button>
          {abilitiesOnThisModel.length > 0 && (
            <ul>
              {abilitiesOnThisModel.map((a) => (
                <li key={a.id}>
                  {a.name}
                  {a.description ? ` — ${a.description}` : ''}
                  <EditButton onClick={() => onEditAbility(a)} />
                  <button type="button" onClick={() => handleRemoveAbility(a.id)}>
                    Remove
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

export default ModelFormPage
