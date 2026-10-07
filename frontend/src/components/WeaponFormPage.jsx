import { useState } from 'react'
import { createWeapon, updateWeapon } from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'

function buildEmptyForm(defaultModelId) {
  return {
    name: '',
    model_id: defaultModelId ? String(defaultModelId) : '',
    damage: '',
    range: '',
    strength: '',
    ap: '',
    attacks: '',
    skill: '',
    weapon_type: '',
    ability_ids: [],
  }
}

function formFromWeapon(weapon) {
  return {
    name: weapon.name,
    model_id: String(weapon.model_id),
    damage: weapon.damage,
    range: weapon.range === null ? '' : String(weapon.range),
    strength: String(weapon.strength),
    ap: String(weapon.ap),
    attacks: String(weapon.attacks),
    skill: String(weapon.skill),
    weapon_type: weapon.weapon_type ?? '',
    ability_ids: weapon.ability_ids,
  }
}

function toPayload(form) {
  return {
    name: form.name,
    model_id: Number(form.model_id),
    damage: form.damage,
    range: form.range === '' ? null : Number(form.range),
    strength: Number(form.strength),
    ap: Number(form.ap),
    attacks: Number(form.attacks),
    skill: Number(form.skill),
    weapon_type: form.weapon_type === '' ? null : form.weapon_type,
    ability_ids: form.ability_ids,
  }
}

function WeaponFormPage({
  editingWeapon,
  defaultModelId,
  models,
  weaponAbilities,
  onSaved,
  onCancel,
}) {
  const [form, setForm] = useState(
    editingWeapon ? formFromWeapon(editingWeapon) : buildEmptyForm(defaultModelId)
  )
  const [error, setError] = useState(null)

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })
  const isMelee = form.weapon_type === 'melee'

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingWeapon) {
        await updateWeapon(editingWeapon.id, toPayload(form))
      } else {
        await createWeapon(toPayload(form))
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingWeapon ? `Edit Weapon #${editingWeapon.id}` : 'Add Weapon'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={form.name} onChange={handleChange('name')} required />
        </Field>
        <Field label="Model">
          <select value={form.model_id} onChange={handleChange('model_id')} required>
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
        <Field label="Damage (e.g. 1, 2, D3, D6, 2D6)">
          <input
            type="text"
            pattern="([0-9]+|[0-9]*D[36])"
            value={form.damage}
            onChange={handleChange('damage')}
            required
          />
        </Field>
        <Field label={`Range${isMelee ? ' (not required for melee)' : ''}`}>
          <input
            type="number"
            value={form.range}
            onChange={handleChange('range')}
            required={!isMelee}
          />
        </Field>
        <Field label="Strength">
          <input type="number" value={form.strength} onChange={handleChange('strength')} required />
        </Field>
        <Field label="AP">
          <input type="number" value={form.ap} onChange={handleChange('ap')} required />
        </Field>
        <Field label="Attacks">
          <input type="number" value={form.attacks} onChange={handleChange('attacks')} required />
        </Field>
        <Field label="Skill (WS/BS)">
          <input type="number" value={form.skill} onChange={handleChange('skill')} required />
        </Field>
        <div className="radio-group">
          Weapon Type
          <label className="radio-option">
            <input
              type="radio"
              name="weapon_type"
              value="melee"
              checked={form.weapon_type === 'melee'}
              onChange={handleChange('weapon_type')}
            />
            Melee
          </label>
          <label className="radio-option">
            <input
              type="radio"
              name="weapon_type"
              value="ranged"
              checked={form.weapon_type === 'ranged'}
              onChange={handleChange('weapon_type')}
            />
            Ranged
          </label>
        </div>
        <label className="field">
          Weapon Abilities
          <MultiSelect
            options={weaponAbilities}
            value={form.ability_ids}
            onChange={(ability_ids) => setForm({ ...form, ability_ids })}
          />
        </label>
        <button type="submit">{editingWeapon ? 'Save Changes' : 'Add Weapon'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default WeaponFormPage
