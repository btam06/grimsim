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
import { skillValue } from '../weaponDisplay'

export const ENHANCEMENT_KINDS = [
  { id: 'enhancement', name: 'Enhancement (carried by a Character)' },
  { id: 'upgrade', name: 'Upgrade (taken by a unit)' },
]

// Who a granted ability reaches - an enhancement's: the bearer, the unit it
// leads, or the bearer's unit whether leading or not; an upgrade's: the unit.
const SCOPES = {
  enhancement: [
    { id: 'bearer', name: 'The bearer' },
    { id: 'led_unit', name: 'The unit it leads' },
    { id: 'bearers_unit', name: "The bearer's unit (leading or not)" },
  ],
  upgrade: [{ id: 'unit', name: 'The unit' }],
}
const SCOPE_NAMES = {
  bearer: 'bearer',
  led_unit: 'led unit',
  bearers_unit: "bearer's unit",
  unit: 'unit',
}
const WEAPON_TYPES = [
  { id: '', name: 'All weapons' },
  { id: 'ranged', name: 'Ranged weapons' },
  { id: 'melee', name: 'Melee weapons' },
]

const EMPTY_WEAPON = {
  name: '',
  weapon_type: 'ranged',
  range: '',
  attacks: '',
  skill: '',
  strength: '',
  ap: '0',
  damage: '',
  ability_ids: [],
}

// e.g. 'TL-4Ø9 (24" A3 BS2+ S11 AP-2 D D3+2)'.
const weaponProfile = (w) =>
  `${w.name} (${w.weapon_type === 'melee' ? 'Melee' : `${w.range}"`} A${w.attacks} ` +
  `${w.weapon_type === 'melee' ? 'WS' : 'BS'} ${skillValue(w.skill)} S${w.strength} AP${w.ap} ` +
  `D${w.damage})`

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
  // Keywords it gives models, and the picker for adding one.
  const [keywordGrants, setKeywordGrants] = useState([])
  const [grantKeywordId, setGrantKeywordId] = useState('')
  const [keywordScope, setKeywordScope] = useState('bearer')
  // Weapons it gives the bearer (enhancements only), and the one being added.
  const [weapons, setWeapons] = useState([])
  const [weaponDraft, setWeaponDraft] = useState(EMPTY_WEAPON)
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
    setKeywordScope(scope)
    setWeaponGrants([])
    setDatasheetGrants([])
    setKeywordGrants([])
    if (newKind !== 'enhancement') setWeapons([])
  }

  const addKeywordGrant = () => {
    if (!grantKeywordId) return
    const id = Number(grantKeywordId)
    setKeywordGrants([
      ...keywordGrants.filter((g) => g.keyword_id !== id),
      { keyword_id: id, scope: keywordScope },
    ])
  }

  const addWeapon = () => {
    const d = weaponDraft
    setWeapons([
      ...weapons,
      {
        ...d,
        range: d.weapon_type === 'melee' || d.range === '' ? null : Number(d.range),
        skill: Number(d.skill),
        strength: Number(d.strength),
        ap: Number(d.ap),
      },
    ])
    setWeaponDraft(EMPTY_WEAPON)
  }
  const draftField = (field) => (e) => setWeaponDraft({ ...weaponDraft, [field]: e.target.value })

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
        granted_keywords: keywordGrants,
        weapons,
      })
      setName('')
      setDescription('')
      setPoints('0')
      setKeywordIds([])
      setExcludedKeywordIds([])
      setWeaponGrants([])
      setDatasheetGrants([])
      setKeywordGrants([])
      setWeapons([])
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
        <div className="checkbox-group">
          Gives keywords
          {keywordGrants.length > 0 && (
            <ul>
              {keywordGrants.map((g, i) => (
                <li key={g.keyword_id}>
                  {keywordName(g.keyword_id)} ({SCOPE_NAMES[g.scope]})
                  <DeleteButton
                    onClick={() => setKeywordGrants(keywordGrants.filter((_, j) => j !== i))}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
        <Field label="Keyword">
          <Select
            options={keywords}
            value={grantKeywordId}
            onChange={setGrantKeywordId}
            placeholder="Select keyword"
          />
        </Field>
        <Field label="For">
          <Select options={SCOPES[kind]} value={keywordScope} onChange={setKeywordScope} />
        </Field>
        <button type="button" disabled={!grantKeywordId} onClick={addKeywordGrant}>
          Add keyword
        </button>
        {kind === 'enhancement' && (
          <>
            <div className="checkbox-group">
              Gives the bearer weapons
              {weapons.length > 0 && (
                <ul>
                  {weapons.map((w, i) => (
                    <li key={i}>
                      {weaponProfile(w)}
                      <DeleteButton onClick={() => setWeapons(weapons.filter((_, j) => j !== i))} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Field label="Weapon name">
              <input value={weaponDraft.name} onChange={draftField('name')} />
            </Field>
            <Field label="Type">
              <Select
                options={[
                  { id: 'ranged', name: 'Ranged' },
                  { id: 'melee', name: 'Melee' },
                ]}
                value={weaponDraft.weapon_type}
                onChange={(weapon_type) => setWeaponDraft({ ...weaponDraft, weapon_type })}
              />
            </Field>
            {weaponDraft.weapon_type === 'ranged' && (
              <Field label="Range">
                <input type="number" value={weaponDraft.range} onChange={draftField('range')} />
              </Field>
            )}
            <Field label="Attacks (e.g. 3, D6)">
              <input value={weaponDraft.attacks} onChange={draftField('attacks')} />
            </Field>
            <Field label={weaponDraft.weapon_type === 'melee' ? 'WS' : 'BS'}>
              <input type="number" value={weaponDraft.skill} onChange={draftField('skill')} />
            </Field>
            <Field label="Strength">
              <input type="number" value={weaponDraft.strength} onChange={draftField('strength')} />
            </Field>
            <Field label="AP">
              <input type="number" value={weaponDraft.ap} onChange={draftField('ap')} />
            </Field>
            <Field label="Damage (e.g. 2, D3+2)">
              <input value={weaponDraft.damage} onChange={draftField('damage')} />
            </Field>
            <label className="field">
              Weapon abilities
              <MultiSelect
                options={weaponAbilities}
                value={weaponDraft.ability_ids}
                onChange={(ability_ids) => setWeaponDraft({ ...weaponDraft, ability_ids })}
              />
            </label>
            <button
              type="button"
              disabled={
                !weaponDraft.name ||
                !weaponDraft.attacks ||
                !weaponDraft.skill ||
                !weaponDraft.strength ||
                !weaponDraft.damage
              }
              onClick={addWeapon}
            >
              Add weapon
            </button>
          </>
        )}
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
            {e.granted_keywords.length > 0 &&
              ` — Gives keywords: ${e.granted_keywords
                .map((g) => `${keywordName(g.keyword_id)} (${SCOPE_NAMES[g.scope]})`)
                .join(', ')}`}
            {e.weapons.length > 0 &&
              ` — Weapons: ${e.weapons
                .map(
                  (w) =>
                    weaponProfile(w) +
                    (w.ability_ids.length
                      ? ` [${w.ability_ids.map(weaponAbilityName).join(', ')}]`
                      : '')
                )
                .join(', ')}`}
            <DeleteButton onClick={() => handleRemove(e.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default EnhancementsPanel
