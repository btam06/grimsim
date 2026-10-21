import { useEffect, useState } from 'react'
import {
  createDetachment,
  deleteDetachment,
  deleteDetachmentRule,
  listDatasheetAbilities,
  listDetachmentRules,
  listDetachments,
  listDispositions,
  listFactions,
  listKeywords,
  listWeaponAbilities,
} from '../api'
import DetachmentRuleForm from './DetachmentRuleForm'
import Field from './Field'
import { DeleteButton } from './IconButtons'
import MultiSelect from './MultiSelect'
import Select from './Select'

function DetachmentsPanel() {
  const [detachments, setDetachments] = useState([])
  const [factions, setFactions] = useState([])
  const [dispositions, setDispositions] = useState([])
  const [rules, setRules] = useState([])
  const [keywords, setKeywords] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [datasheetAbilities, setDatasheetAbilities] = useState([])
  const [name, setName] = useState('')
  const [factionId, setFactionId] = useState('')
  const [dp, setDp] = useState('')
  const [dispositionIds, setDispositionIds] = useState([])
  const [error, setError] = useState(null)

  const refresh = () => listDetachments().then(setDetachments).catch((err) => setError(err.message))
  const refreshRules = () =>
    listDetachmentRules().then(setRules).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    refreshRules()
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
    listWeaponAbilities().then(setWeaponAbilities).catch((err) => setError(err.message))
    listDatasheetAbilities().then(setDatasheetAbilities).catch((err) => setError(err.message))
    listFactions().then(setFactions).catch((err) => setError(err.message))
    listDispositions()
      .then(setDispositions)
      .catch((err) => setError(err.message))
  }, [])

  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
  const dispositionName = (id) => dispositions.find((d) => d.id === id)?.name ?? `#${id}`
  const keywordName = (id) => keywords.find((k) => k.id === id)?.name ?? `#${id}`
  // e.g. "Stealth Optimisation — SKITARII + INFANTRY or IRONSTRIDER
  // BALLISTARII units — grants Stealth".
  const ruleLabel = (rule) => {
    const what = rule.per_model ? 'model' : 'unit'
    const units =
      rule.keyword_option_ids.length > 0
        ? `${rule.keyword_option_ids
            .map((option) => option.map(keywordName).sort().join(' + '))
            .join(' or ')} ${what}s`
        : `every ${what}`
    const grants = [
      ...rule.datasheet_ability_ids.map(
        (id) => datasheetAbilities.find((a) => a.id === id)?.name ?? `#${id}`
      ),
      ...rule.weapon_abilities.map(
        (g) =>
          (weaponAbilities.find((a) => a.id === g.weapon_ability_id)?.name ??
            `#${g.weapon_ability_id}`) + (g.weapon_type ? ` (${g.weapon_type} weapons)` : '')
      ),
    ]
    return `${rule.name} — ${units}${grants.length ? ` — grants ${grants.join(', ')}` : ''}`
  }

  const handleRemoveRule = async (id) => {
    setError(null)
    try {
      await deleteDetachmentRule(id)
      refreshRules()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!factionId) {
      setError('Faction is required')
      return
    }
    try {
      await createDetachment({
        name,
        faction_id: Number(factionId),
        dp: Number(dp),
        disposition_ids: dispositionIds,
      })
      setName('')
      setFactionId('')
      setDp('')
      setDispositionIds([])
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteDetachment(id)
      refresh()
      refreshRules()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Detachments</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Faction">
          <Select options={factions} value={factionId} onChange={setFactionId} placeholder="Select faction" />
        </Field>
        <Field label="DP">
          <input type="number" value={dp} onChange={(e) => setDp(e.target.value)} required />
        </Field>
        <label className="field">
          Dispositions
          <MultiSelect
            options={dispositions}
            value={dispositionIds}
            onChange={setDispositionIds}
          />
        </label>
        <button type="submit">Add Detachment</button>
      </form>
      <ul>
        {detachments.map((d) => (
          <li key={d.id}>
            {d.name} ({factionName(d.faction_id)}) — DP {d.dp}
            {d.disposition_ids.length > 0 &&
              ` — ${d.disposition_ids.map(dispositionName).join(', ')}`}
            <button type="button" onClick={() => handleRemove(d.id)}>
              Remove
            </button>
            {rules.some((r) => r.detachment_id === d.id) && (
              <ul>
                {rules
                  .filter((r) => r.detachment_id === d.id)
                  .map((r) => (
                    <li key={r.id} title={r.description ?? ''}>
                      Rule: {ruleLabel(r)}
                      <DeleteButton onClick={() => handleRemoveRule(r.id)} />
                    </li>
                  ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <h3>Add Detachment Rule</h3>
      <DetachmentRuleForm
        detachments={detachments}
        keywords={keywords}
        weaponAbilities={weaponAbilities}
        datasheetAbilities={datasheetAbilities}
        onSaved={refreshRules}
        onError={setError}
      />
    </section>
  )
}

export default DetachmentsPanel
