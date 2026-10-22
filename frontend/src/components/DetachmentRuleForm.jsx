import { useState } from 'react'
import { createDetachmentRule } from '../api'
import Field from './Field'
import { DeleteButton } from './IconButtons'
import MultiSelect from './MultiSelect'
import Select from './Select'

const WEAPON_TYPES = [
  { id: '', name: 'All weapons' },
  { id: 'ranged', name: 'Ranged weapons' },
  { id: 'melee', name: 'Melee weapons' },
]

// Adds a rule to a detachment: the units it reaches (every model having all
// of one keyword option; none means every unit) and the abilities it grants.
function DetachmentRuleForm({
  detachments,
  keywords,
  weaponAbilities,
  datasheetAbilities,
  onSaved,
  onError,
}) {
  const [detachmentId, setDetachmentId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [keywordOptions, setKeywordOptions] = useState([])
  const [optionDraft, setOptionDraft] = useState([])
  const [datasheetAbilityIds, setDatasheetAbilityIds] = useState([])
  const [grantedKeywordIds, setGrantedKeywordIds] = useState([])
  const [weaponGrants, setWeaponGrants] = useState([])
  const [weaponAbilityId, setWeaponAbilityId] = useState('')
  const [weaponType, setWeaponType] = useState('')
  const [perModel, setPerModel] = useState(false)

  const keywordName = (id) => keywords.find((k) => k.id === id)?.name ?? `#${id}`
  const weaponAbilityName = (id) => weaponAbilities.find((a) => a.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    onError(null)
    try {
      await createDetachmentRule({
        detachment_id: Number(detachmentId),
        name,
        description: description || null,
        keyword_option_ids: keywordOptions,
        weapon_abilities: weaponGrants,
        datasheet_ability_ids: datasheetAbilityIds,
        granted_keyword_ids: grantedKeywordIds,
        per_model: perModel,
      })
      setName('')
      setDescription('')
      setKeywordOptions([])
      setDatasheetAbilityIds([])
      setGrantedKeywordIds([])
      setWeaponGrants([])
      setPerModel(false)
      onSaved()
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Field label="Detachment">
        <Select
          options={detachments}
          value={detachmentId}
          onChange={setDetachmentId}
          placeholder="Select detachment"
        />
      </Field>
      <Field label="Rule name">
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Description (optional)">
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={perModel}
          onChange={(e) => setPerModel(e.target.checked)}
        />
        Reaches models, not units (e.g. "friendly TECH-PRIEST models have...")
      </label>
      <div className="checkbox-group">
        {perModel
          ? 'Models it reaches (a model needs all of one option; none means every model)'
          : 'Units it reaches (every model needs all of one option; none means every unit)'}
        {keywordOptions.length > 0 && (
          <ul>
            {keywordOptions.map((option, i) => (
              <li key={i}>
                {option.map(keywordName).sort().join(' + ')}
                <DeleteButton
                  onClick={() => setKeywordOptions(keywordOptions.filter((_, j) => j !== i))}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      <label className="field">
        Option keywords
        <MultiSelect options={keywords} value={optionDraft} onChange={setOptionDraft} />
      </label>
      <button
        type="button"
        disabled={optionDraft.length === 0}
        onClick={() => {
          setKeywordOptions([...keywordOptions, optionDraft])
          setOptionDraft([])
        }}
      >
        Add keyword option
      </button>
      <label className="field">
        Grants datasheet abilities
        <MultiSelect
          options={datasheetAbilities}
          value={datasheetAbilityIds}
          onChange={setDatasheetAbilityIds}
        />
      </label>
      <label className="field">
        Grants keywords
        <MultiSelect options={keywords} value={grantedKeywordIds} onChange={setGrantedKeywordIds} />
      </label>
      <div className="checkbox-group">
        Grants weapon abilities
        {weaponGrants.length > 0 && (
          <ul>
            {weaponGrants.map((g, i) => (
              <li key={g.weapon_ability_id}>
                {weaponAbilityName(g.weapon_ability_id)}
                {g.weapon_type && ` (${g.weapon_type} weapons)`}
                <DeleteButton
                  onClick={() => setWeaponGrants(weaponGrants.filter((_, j) => j !== i))}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      <Field label="Weapon ability">
        <Select
          options={weaponAbilities}
          value={weaponAbilityId}
          onChange={setWeaponAbilityId}
          placeholder="Select weapon ability"
        />
      </Field>
      <Field label="On">
        <Select options={WEAPON_TYPES} value={weaponType} onChange={setWeaponType} />
      </Field>
      <button
        type="button"
        disabled={!weaponAbilityId}
        onClick={() => {
          const id = Number(weaponAbilityId)
          setWeaponGrants([
            ...weaponGrants.filter((g) => g.weapon_ability_id !== id),
            { weapon_ability_id: id, weapon_type: weaponType || null },
          ])
        }}
      >
        Add weapon ability
      </button>
      <button type="submit">Add Rule</button>
    </form>
  )
}

export default DetachmentRuleForm
