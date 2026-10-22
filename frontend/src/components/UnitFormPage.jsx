import { useEffect, useState } from 'react'
import {
  createUnit,
  listAvailableEnhancements,
  listAvailableUpgrades,
  listEnhancements,
  listSelectableRules,
  updateUnit,
} from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'
import Select from './Select'

// enhancement_id: '' for none, else the id as a string (as Select uses).
const EMPTY_SLOT = { model_id: '', weapon_ids: [], wargear_ids: [], enhancement_id: '' }

function slotsFromUnit(unit) {
  return unit.unit_models.map((um) => ({
    model_id: String(um.model_id),
    weapon_ids: um.weapon_ids,
    wargear_ids: um.wargear_ids,
    enhancement_id: um.enhancement_id === null ? '' : String(um.enhancement_id),
  }))
}

// A model's only ranged weapon (or only melee weapon) is always carried, so
// it's selected automatically and can't be unselected. Ranged and melee are
// checked separately; a weapon with no type counts as ranged.
function requiredWeaponIds(modelWeapons) {
  const ranged = modelWeapons.filter((w) => w.weapon_type !== 'melee')
  const melee = modelWeapons.filter((w) => w.weapon_type === 'melee')
  return [ranged, melee].filter((group) => group.length === 1).map((group) => group[0].id)
}

function UnitFormPage({
  editingUnit,
  defaultListId,
  models,
  modelOptions,
  weapons,
  wargear,
  factionUnits,
  onSaved,
  onCancel,
}) {
  const [factionUnitId, setFactionUnitId] = useState(
    editingUnit ? String(editingUnit.faction_unit_id) : ''
  )
  const [points, setPoints] = useState(editingUnit ? String(editingUnit.points) : '')
  const [listId] = useState(() => {
    if (editingUnit) return editingUnit.list_id === null ? '' : String(editingUnit.list_id)
    return defaultListId ? String(defaultListId) : ''
  })
  const [slot, setSlot] = useState(EMPTY_SLOT)
  const [quantity, setQuantity] = useState('1')
  const [slots, setSlots] = useState(editingUnit ? slotsFromUnit(editingUnit) : [])
  const [upgradeId, setUpgradeId] = useState(
    editingUnit?.upgrade_id ? String(editingUnit.upgrade_id) : ''
  )
  // Every enhancement (for names), and the ones the server says the model
  // being added could carry / this unit could take in its list.
  const [enhancements, setEnhancements] = useState([])
  const [slotEnhancements, setSlotEnhancements] = useState([])
  const [upgrades, setUpgrades] = useState([])
  // Detachment rules this unit could be selected for, and the ones it is.
  const [selectableRules, setSelectableRules] = useState([])
  const [selectedRuleIds, setSelectedRuleIds] = useState(editingUnit?.selected_rule_ids ?? [])
  const selectedRuleKey = selectedRuleIds.join(',')
  const [error, setError] = useState(null)
  const unitId = editingUnit?.id

  useEffect(() => {
    listEnhancements().then(setEnhancements).catch((err) => setError(err.message))
  }, [])

  // Enhancements are only offered when adding a model, and only ones it can
  // carry (a CHARACTER, from the list's detachments, not taken elsewhere).
  useEffect(() => {
    if (!listId || !slot.model_id) {
      setSlotEnhancements([])
      return
    }
    let cancelled = false
    listAvailableEnhancements(listId, slot.model_id, unitId, selectedRuleIds)
      .then((available) => !cancelled && setSlotEnhancements(available))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listId, slot.model_id, unitId, selectedRuleKey])

  // Upgrades depend on every model in the unit, so re-check them as models
  // are added or removed, dropping the chosen one if it no longer applies.
  const slotModelIds = slots.map((s) => s.model_id).join(',')
  useEffect(() => {
    if (!listId || slots.length === 0) {
      setUpgrades([])
      setUpgradeId('')
      return
    }
    let cancelled = false
    listAvailableUpgrades(
      listId,
      slots.map((s) => s.model_id),
      unitId,
      selectedRuleIds
    )
      .then((available) => {
        if (cancelled) return
        setUpgrades(available)
        setUpgradeId((id) => (available.some((u) => String(u.id) === id) ? id : ''))
      })
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listId, slotModelIds, unitId, selectedRuleKey])

  // Rules the unit can be selected for depend on its models too; drop any
  // selection that no longer applies.
  useEffect(() => {
    if (!listId || slots.length === 0) {
      setSelectableRules([])
      setSelectedRuleIds([])
      return
    }
    let cancelled = false
    listSelectableRules(
      listId,
      slots.map((s) => s.model_id),
      unitId
    )
      .then((rules) => {
        if (cancelled) return
        setSelectableRules(rules)
        const ids = new Set(rules.map((r) => r.id))
        setSelectedRuleIds((selected) => selected.filter((id) => ids.has(id)))
      })
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listId, slotModelIds, unitId])
  const toggleRule = (id) =>
    setSelectedRuleIds((selected) =>
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    )

  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const enhancementLabel = (id) => {
    const enhancement = enhancements.find((e) => String(e.id) === id)
    return enhancement ? `${enhancement.name} (+${enhancement.points} pts)` : `#${id}`
  }
  // An enhancement can only be carried once, so leave out ones already on a
  // model in this unit.
  const enhancementOptionsForSlot = slotEnhancements
    .filter((e) => !slots.some((s) => s.enhancement_id === String(e.id)))
    .map((e) => ({ id: e.id, name: `${e.name} (+${e.points} pts)` }))

  const weaponOptionsForSlot = weapons.filter((w) => String(w.model_id) === slot.model_id)
  const wargearOptionsForSlot = wargear.filter((g) => String(g.model_id) === slot.model_id)
  const requiredWeaponIdsForSlot = requiredWeaponIds(weaponOptionsForSlot)

  const addSlot = () => {
    if (!slot.model_id) return
    // A model with an enhancement is added on its own.
    const count = slot.enhancement_id ? 1 : Math.max(1, Number(quantity) || 1)
    setSlots([...slots, ...Array.from({ length: count }, () => slot)])
    // Keep the model/weapons/wargear selected, so adding more of the same (or
    // a variation on it) doesn't mean re-picking everything - but not the
    // enhancement, which can only be carried once.
    setSlot({ ...slot, enhancement_id: '' })
    setQuantity('1')
  }

  const removeSlot = (index) => setSlots(slots.filter((_, i) => i !== index))

  const selectModel = (model_id) => {
    const modelWeapons = weapons.filter((w) => String(w.model_id) === model_id)
    setSlot({
      model_id,
      weapon_ids: requiredWeaponIds(modelWeapons),
      wargear_ids: [],
      enhancement_id: '',
    })
  }

  const toggleSlotWeapon = (weaponId) => {
    if (requiredWeaponIdsForSlot.includes(weaponId)) return
    setSlot({
      ...slot,
      weapon_ids: slot.weapon_ids.includes(weaponId)
        ? slot.weapon_ids.filter((id) => id !== weaponId)
        : [...slot.weapon_ids, weaponId],
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!factionUnitId) {
      setError('Faction Unit is required')
      return
    }
    try {
      const payload = {
        faction_unit_id: Number(factionUnitId),
        points: Number(points),
        list_id: listId === '' ? null : Number(listId),
        unit_models: slots.map((s) => ({
          model_id: Number(s.model_id),
          weapon_ids: s.weapon_ids,
          wargear_ids: s.wargear_ids,
          enhancement_id: s.enhancement_id ? Number(s.enhancement_id) : null,
        })),
        upgrade_id: upgradeId ? Number(upgradeId) : null,
        selected_rule_ids: selectedRuleIds,
      }
      if (editingUnit) {
        await updateUnit(editingUnit.id, payload)
      } else {
        await createUnit(payload)
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingUnit ? `Edit Unit #${editingUnit.id}` : 'Add Unit'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Faction Unit">
          <Select
            options={factionUnits}
            value={factionUnitId}
            onChange={setFactionUnitId}
            placeholder="Select faction unit"
          />
        </Field>
        <Field label="Points">
          <input type="number" value={points} onChange={(e) => setPoints(e.target.value)} required />
        </Field>
        {upgrades.length > 0 && (
          <Field label="Upgrade">
            <Select
              options={[
                { id: '', name: 'None' },
                ...upgrades.map((u) => ({ id: u.id, name: `${u.name} (+${u.points} pts)` })),
              ]}
              value={upgradeId}
              onChange={setUpgradeId}
            />
          </Field>
        )}

        {selectableRules.length > 0 && (
          <div className="checkbox-group">
            Selected for detachment rules
            {selectableRules.map((r) => {
              const full = r.selected_elsewhere >= r.selection_limit
              const selected = selectedRuleIds.includes(r.id)
              return (
                <label key={r.id} className="checkbox-field" title={r.description ?? ''}>
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={full && !selected}
                    onChange={() => toggleRule(r.id)}
                  />
                  {r.name} ({r.selected_elsewhere + (selected ? 1 : 0)}/{r.selection_limit} in
                  this list)
                </label>
              )
            })}
          </div>
        )}

        {slots.length > 0 && (
          <ul>
            {slots.map((s, i) => (
              <li key={i}>
                {modelName(Number(s.model_id))}
                {s.weapon_ids.length > 0 && ` — ${s.weapon_ids.map(weaponName).join(', ')}`}
                {s.wargear_ids.length > 0 && ` — ${s.wargear_ids.map(wargearName).join(', ')}`}
                {s.enhancement_id && ` — Enhancement: ${enhancementLabel(s.enhancement_id)}`}
                <button type="button" onClick={() => removeSlot(i)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <Field label="Add model to unit">
          <Select
            options={modelOptions}
            value={slot.model_id}
            onChange={selectModel}
            placeholder="Select model"
          />
        </Field>
        <div className="checkbox-group">
          Weapons
          {weaponOptionsForSlot.length === 0 && (
            <p className="hint">Select a model to see its weapons</p>
          )}
          <div className="checkbox-grid">
            {weaponOptionsForSlot.map((w) => (
              <label key={w.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={slot.weapon_ids.includes(w.id)}
                  disabled={requiredWeaponIdsForSlot.includes(w.id)}
                  onChange={() => toggleSlotWeapon(w.id)}
                />
                {w.name}
              </label>
            ))}
          </div>
        </div>
        <label className="field">
          Wargear
          <MultiSelect
            options={wargearOptionsForSlot}
            value={slot.wargear_ids}
            onChange={(wargear_ids) => setSlot({ ...slot, wargear_ids })}
          />
        </label>
        {enhancementOptionsForSlot.length > 0 && (
          <Field label="Enhancement">
            <Select
              options={[{ id: '', name: 'None' }, ...enhancementOptionsForSlot]}
              value={slot.enhancement_id}
              onChange={(enhancement_id) => setSlot({ ...slot, enhancement_id })}
            />
          </Field>
        )}
        <Field label="Quantity">
          <input
            type="number"
            min="1"
            value={slot.enhancement_id ? '1' : quantity}
            disabled={Boolean(slot.enhancement_id)}
            onChange={(e) => setQuantity(e.target.value)}
          />
        </Field>
        <button type="button" disabled={!slot.model_id} onClick={addSlot}>
          Add Model to Unit
        </button>

        <button type="submit">{editingUnit ? 'Save Changes' : 'Add Unit'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default UnitFormPage
