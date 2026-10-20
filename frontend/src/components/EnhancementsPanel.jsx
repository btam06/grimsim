import { useEffect, useState } from 'react'
import {
  createEnhancement,
  deleteEnhancement,
  listDatasheetAbilities,
  listDetachments,
  listEnhancements,
  listKeywords,
  listWeaponAbilities,
} from '../api'
import Field from './Field'
import { DeleteButton } from './IconButtons'
import MultiSelect from './MultiSelect'
import Select from './Select'

export const ENHANCEMENT_KINDS = [
  { id: 'enhancement', name: 'Enhancement (carried by a Character)' },
  { id: 'upgrade', name: 'Upgrade (taken by a unit)' },
]

// Who a granted ability reaches - an enhancement's: the bearer, or the unit
// it leads; an upgrade's: the unit.
const SCOPES = {
  enhancement: [
    { id: 'bearer', name: 'The bearer' },
    { id: 'led_unit', name: 'The unit it leads' },
  ],
  upgrade: [{ id: 'unit', name: 'The unit' }],
}
const SCOPE_NAMES = { bearer: 'bearer', led_unit: 'led unit', unit: 'unit' }
const WEAPON_TYPES = [
  { id: '', name: 'All weapons' },
  { id: 'ranged', name: 'Ranged weapons' },
  { id: 'melee', name: 'Melee weapons' },
]

function EnhancementsPanel() {
  const [enhancements, setEnhancements] = useState([])
  const [detachments, setDetachments] = useState([])
  const [keywords, setKeywords] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [points, setPoints] = useState('0')
  const [kind, setKind] = useState('enhancement')
  const [detachmentId, setDetachmentId] = useState('')
  const [keywordIds, setKeywordIds] = useState([])
  const [excludedKeywordIds, setExcludedKeywordIds] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [datasheetAbilities, setDatasheetAbilities] = useState([])
  // Abilities it grants in combat, and the pickers for adding one.
  const [weaponGrants, setWeaponGrants] = useState([])
  const [datasheetGrants, setDatasheetGrants] = useState([])
  const [weaponAbilityId, setWeaponAbilityId] = useState('')
  const [weaponType, setWeaponType] = useState('')
  const [weaponScope, setWeaponScope] = useState('bearer')
  const [datasheetAbilityId, setDatasheetAbilityId] = useState('')
  const [datasheetScope, setDatasheetScope] = useState('bearer')
  const [error, setError] = useState(null)

  const refresh = () =>
    listEnhancements().then(setEnhancements).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listDetachments().then(setDetachments).catch((err) => setError(err.message))
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
    listWeaponAbilities().then(setWeaponAbilities).catch((err) => setError(err.message))
    listDatasheetAbilities().then(setDatasheetAbilities).catch((err) => setError(err.message))
  }, [])

  // Scopes depend on the kind, so changing it starts the grants over.
  const changeKind = (newKind) => {
    setKind(newKind)
    const scope = SCOPES[newKind][0].id
    setWeaponScope(scope)
    setDatasheetScope(scope)
    setWeaponGrants([])
    setDatasheetGrants([])
  }

  const addWeaponGrant = () => {
    if (!weaponAbilityId) return
    const id = Number(weaponAbilityId)
    setWeaponGrants([
      ...weaponGrants.filter((g) => g.weapon_ability_id !== id),
      { weapon_ability_id: id, weapon_type: weaponType || null, scope: weaponScope },
    ])
  }

  const addDatasheetGrant = () => {
    if (!datasheetAbilityId) return
    const id = Number(datasheetAbilityId)
    setDatasheetGrants([
      ...datasheetGrants.filter((g) => g.datasheet_ability_id !== id),
      { datasheet_ability_id: id, scope: datasheetScope },
    ])
  }

  const weaponAbilityName = (id) => weaponAbilities.find((a) => a.id === id)?.name ?? `#${id}`
  const datasheetAbilityName = (id) =>
    datasheetAbilities.find((a) => a.id === id)?.name ?? `#${id}`
  // e.g. "Sustained 1 (ranged weapons, led unit)", "Stealth (bearer)".
  const grantLabels = (e) => [
    ...e.weapon_abilities.map(
      (g) =>
        `${weaponAbilityName(g.weapon_ability_id)} (${
          g.weapon_type ? `${g.weapon_type} weapons, ` : ''
        }${SCOPE_NAMES[g.scope]})`
    ),
    ...e.datasheet_abilities.map(
      (g) => `${datasheetAbilityName(g.datasheet_ability_id)} (${SCOPE_NAMES[g.scope]})`
    ),
  ]

  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const keywordName = (id) => keywords.find((k) => k.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createEnhancement({
        name,
        description: description || null,
        points: Number(points),
        kind,
        detachment_id: Number(detachmentId),
        keyword_ids: keywordIds,
        excluded_keyword_ids: excludedKeywordIds,
        weapon_abilities: weaponGrants,
        datasheet_abilities: datasheetGrants,
      })
      setName('')
      setDescription('')
      setPoints('0')
      setKeywordIds([])
      setExcludedKeywordIds([])
      setWeaponGrants([])
      setDatasheetGrants([])
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteEnhancement(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Enhancements</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Points">
          <input
            type="number"
            min="0"
            value={points}
            onChange={(e) => setPoints(e.target.value)}
            required
          />
        </Field>
        <Field label="Kind">
          <Select options={ENHANCEMENT_KINDS} value={kind} onChange={changeKind} />
        </Field>
        <Field label="Detachment">
          <Select
            options={detachments}
            value={detachmentId}
            onChange={setDetachmentId}
            placeholder="Select detachment"
          />
        </Field>
        <label className="field">
          {kind === 'enhancement'
            ? 'Required keywords (the model carrying it needs all of them)'
            : 'Required keywords (every model in the unit needs all of them)'}
          <MultiSelect options={keywords} value={keywordIds} onChange={setKeywordIds} />
        </label>
        <label className="field">
          Excluded keywords (any one of them rules it out)
          <MultiSelect
            options={keywords}
            value={excludedKeywordIds}
            onChange={setExcludedKeywordIds}
          />
        </label>
        <div className="checkbox-group">
          Grants in combat
          {weaponGrants.length + datasheetGrants.length === 0 && (
            <p className="hint">Nothing yet</p>
          )}
          <ul>
            {grantLabels({ weapon_abilities: weaponGrants, datasheet_abilities: datasheetGrants }).map(
              (label, i) => (
                <li key={label}>
                  {label}
                  <DeleteButton
                    onClick={() =>
                      i < weaponGrants.length
                        ? setWeaponGrants(weaponGrants.filter((_, j) => j !== i))
                        : setDatasheetGrants(
                            datasheetGrants.filter((_, j) => j !== i - weaponGrants.length)
                          )
                    }
                  />
                </li>
              )
            )}
          </ul>
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
        <Field label="For">
          <Select options={SCOPES[kind]} value={weaponScope} onChange={setWeaponScope} />
        </Field>
        <button type="button" disabled={!weaponAbilityId} onClick={addWeaponGrant}>
          Add weapon ability
        </button>
        <Field label="Datasheet ability">
          <Select
            options={datasheetAbilities}
            value={datasheetAbilityId}
            onChange={setDatasheetAbilityId}
            placeholder="Select datasheet ability"
          />
        </Field>
        <Field label="For">
          <Select options={SCOPES[kind]} value={datasheetScope} onChange={setDatasheetScope} />
        </Field>
        <button type="button" disabled={!datasheetAbilityId} onClick={addDatasheetGrant}>
          Add datasheet ability
        </button>
        <button type="submit">Add Enhancement</button>
      </form>
      <ul>
        {enhancements.map((e) => (
          <li key={e.id}>
            {e.name} — {e.points} pts — {e.kind === 'upgrade' ? 'Upgrade' : 'Enhancement'} —{' '}
            {detachmentName(e.detachment_id)}
            {e.description ? ` — ${e.description}` : ''}
            {e.keyword_ids.length > 0 && ` — Requires: ${e.keyword_ids.map(keywordName).join(', ')}`}
            {e.excluded_keyword_ids.length > 0 &&
              ` — Excludes: ${e.excluded_keyword_ids.map(keywordName).join(', ')}`}
            {grantLabels(e).length > 0 && ` — Grants: ${grantLabels(e).join(', ')}`}
            <DeleteButton onClick={() => handleRemove(e.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default EnhancementsPanel
