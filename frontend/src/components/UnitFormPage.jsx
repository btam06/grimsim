import { useEffect, useState } from 'react'
import {
  createUnit,
  getLoadout,
  priceUnit,
  listAvailableEnhancements,
  listAvailableUpgrades,
  listEnhancements,
  listSelectableRules,
  listUnits,
  updateUnit,
} from '../api'
import CardTextAccordion from './CardTextAccordion'
import ChoiceBoxes from './ChoiceBoxes'
import Field from './Field'
import { RemoveButton } from './IconButtons'
import MultiSelect from './MultiSelect'
import Select from './Select'
import {
  EMPTY_LOADOUT,
  composedSlot,
  ordered,
  partFor,
  startingSlots,
  variantLabel,
  variantOf,
  withModel,
  withSlotAs,
} from '../loadouts'

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
  // The bodyguard unit this leader or support unit is attached to ('' for
  // none), and the list's units it could be: of a datasheet it can lead.
  const [attachedToId, setAttachedToId] = useState(
    editingUnit?.attached_to_id ? String(editingUnit.attached_to_id) : ''
  )
  const [listUnitsInList, setListUnitsInList] = useState([])
  useEffect(() => {
    if (!listId) return
    listUnits()
      .then((units) => setListUnitsInList(units.filter((u) => String(u.list_id) === listId)))
      .catch(() => setListUnitsInList([]))
  }, [listId])
  const bodyguardIds = factionUnits.find((f) => String(f.id) === factionUnitId)?.bodyguard_ids ?? []
  const factionUnitName = (id) => factionUnits.find((f) => f.id === id)?.name ?? `#${id}`
  const bodyguardOptions = listUnitsInList.filter(
    (u) =>
      bodyguardIds.includes(u.faction_unit_id) &&
      u.attached_to_id === null &&
      u.id !== editingUnit?.id
  )
  const selectedRuleKey = selectedRuleIds.join(',')
  const [error, setError] = useState(null)
  const unitId = editingUnit?.id

  // What the datasheet's units can be made of (its composition and wargear
  // options, from the data). A new unit starts as composed - the fewest of
  // each model, as equipped - so a datasheet with nothing to decide (one
  // CHARACTER, as equipped) is already complete.
  const [loadout, setLoadout] = useState(EMPTY_LOADOUT)
  useEffect(() => {
    if (!factionUnitId) {
      setLoadout(EMPTY_LOADOUT)
      return
    }
    let cancelled = false
    getLoadout(factionUnitId)
      .then((found) => {
        if (cancelled) return
        setLoadout(found)
        setSlot(EMPTY_SLOT)
        setSlots((current) => ordered(found, editingUnit ? current : startingSlots(found)))
      })
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factionUnitId])
  const composed = loadout.composition.length > 0
  const countOf = (modelId) => slots.filter((s) => s.model_id === String(modelId)).length
  // (Kept in order: the sergeant first.)
  const putSlots = (next) => setSlots(ordered(loadout, next))
  // The datasheet's models, when the data says which (free-form datasheets).
  const datasheetModelOptions =
    loadout.model_ids.length === 0
      ? modelOptions
      : models.filter((m) => loadout.model_ids.includes(m.id))
  // A composed unit with all it can have of every model: nothing more to add.
  const full = composed && loadout.composition.every((p) => countOf(p.model_id) >= p.max)
  // For a composed datasheet, models are added as equipped (any of its models
  // the unit has room for, sergeant first), then each one's loadout is
  // picked under it.
  const addable = composed ? loadout.composition.filter((p) => countOf(p.model_id) < p.max) : []
  const addableKey = addable.map((p) => p.model_id).join(',')
  useEffect(() => {
    if (!composed || addable.some((p) => String(p.model_id) === slot.model_id)) return
    setSlot(addable.length > 0 ? composedSlot(addable[0]) : EMPTY_SLOT)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [composed, addableKey])
  // A model's loadouts it can switch to without breaking the datasheet's
  // limits (and the one it has); none shown unless there's a choice.
  const loadoutChoices = (s, index) => {
    const current = variantOf(loadout, s)
    const choices = loadout.variants.filter(
      (v) =>
        String(v.model_id) === s.model_id &&
        (v === current || withSlotAs(loadout, slots, index, v) !== null)
    )
    return { current, choices: choices.length > 1 ? choices : [] }
  }
  // Which model's loadouts are open (one at a time).
  const [openSlot, setOpenSlot] = useState(null)
  const changeLoadout = (index, variant) => {
    const next = withSlotAs(loadout, slots, index, variant)
    if (next) putSlots(next)
  }

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
  const itemNameOf = (kind, id) => (kind === 'weapon' ? weaponName(id) : wargearName(id))
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
    // (Adding can reorder the models.)
    setOpenSlot(null)
    // A model with an enhancement is added on its own.
    const count = slot.enhancement_id ? 1 : Math.max(1, Number(quantity) || 1)
    if (composed) {
      // As many as fit, as equipped.
      const part = partFor(loadout, slot.model_id)
      let next = slots
      for (let i = 0; i < count; i++) {
        const added = part && withModel(loadout, next, part)
        if (!added) break
        next = added
      }
      if (slot.enhancement_id) {
        const at = next.findLastIndex((s, i) => s !== slots[i] && s.model_id === slot.model_id)
        if (at !== -1)
          next = next.map((s, i) => (i === at ? { ...s, enhancement_id: slot.enhancement_id } : s))
      }
      putSlots(next)
      setSlot({ ...slot, enhancement_id: '' })
      setQuantity('1')
      return
    }
    putSlots([...slots, ...Array.from({ length: count }, () => slot)])
    // Keep the model/weapons/wargear selected, so adding more of the same (or
    // a variation on it) doesn't mean re-picking everything - but not the
    // enhancement, which can only be carried once.
    setSlot({ ...slot, enhancement_id: '' })
    setQuantity('1')
  }

  const removeSlot = (index) => {
    putSlots(slots.filter((_, i) => i !== index))
    setOpenSlot(null)
  }

  // A model starts with its default weapons (its datasheet's "This model is
  // equipped with: ...") and any it always carries.
  const selectModel = (model_id) => {
    const modelWeapons = weapons.filter((w) => String(w.model_id) === model_id)
    const defaults = modelWeapons.filter((w) => w.is_default).map((w) => w.id)
    setSlot({
      model_id,
      weapon_ids: [...new Set([...defaults, ...requiredWeaponIds(modelWeapons)])],
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

  const buildPayload = () => ({
    faction_unit_id: Number(factionUnitId),
    list_id: listId === '' ? null : Number(listId),
    unit_models: slots.map((s) => ({
      model_id: Number(s.model_id),
      weapon_ids: s.weapon_ids,
      wargear_ids: s.wargear_ids,
      enhancement_id: s.enhancement_id ? Number(s.enhancement_id) : null,
    })),
    upgrade_id: upgradeId ? Number(upgradeId) : null,
    selected_rule_ids: selectedRuleIds,
    attached_to_id: attachedToId ? Number(attachedToId) : null,
  })

  // The unit's points as it's built (priced by the server as saving would);
  // null while it's being worked out. Its enhancements and upgrade are added
  // on top, as the list counts them.
  const [points, setPoints] = useState(editingUnit ? editingUnit.points : 0)
  const pricedKey = JSON.stringify([
    factionUnitId,
    listId,
    slots.map((s) => [s.model_id, s.weapon_ids, s.wargear_ids]),
  ])
  useEffect(() => {
    if (!factionUnitId || slots.length === 0) {
      setPoints(0)
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      priceUnit(buildPayload(), editingUnit?.id)
        .then((priced) => !cancelled && setPoints(priced.points))
        .catch(() => !cancelled && setPoints(null))
    }, 150)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pricedKey])
  const enhancementPoints = slots.reduce(
    (sum, s) => sum + (enhancements.find((e) => String(e.id) === s.enhancement_id)?.points ?? 0),
    0
  )
  const upgradePoints = upgrades.find((u) => String(u.id) === upgradeId)?.points ?? 0
  const extraPoints = enhancementPoints + upgradePoints

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!factionUnitId) {
      setError('Faction Unit is required')
      return
    }
    try {
      const payload = buildPayload()
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
        {/* Worked out by the server from the Munitorum Field Manual as it's
            saved - not editable. */}
        <Field label="Points">
          <span className="hint">
            {points === null ? "Can't be priced yet" : `${points + extraPoints} pts`}
            {points !== null &&
              extraPoints > 0 &&
              ` (${points} + ${extraPoints} enhancements and upgrades)`}
          </span>
        </Field>
        {listId && bodyguardIds.length > 0 && (
          // A leader or support unit leads a bodyguard unit for the battle
          // (Core Rules 19.01): one of a datasheet it can lead.
          <Field label="Attached to">
            <Select
              options={[
                { id: '', name: 'Not attached' },
                ...bodyguardOptions.map((u) => ({
                  id: String(u.id),
                  name: `${factionUnitName(u.faction_unit_id)} — ${u.points}pts`,
                })),
              ]}
              value={attachedToId}
              onChange={setAttachedToId}
            />
          </Field>
        )}
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
            {slots.map((s, i) => {
              const { current, choices } = composed
                ? loadoutChoices(s, i)
                : { current: undefined, choices: [] }
              const name = modelName(Number(s.model_id))
              const description = (
                <>
                  {name}
                  {s.weapon_ids.length > 0 && ` — ${s.weapon_ids.map(weaponName).join(', ')}`}
                  {s.wargear_ids.length > 0 && ` — ${s.wargear_ids.map(wargearName).join(', ')}`}
                  {s.enhancement_id && ` — Enhancement: ${enhancementLabel(s.enhancement_id)}`}
                </>
              )
              return (
                <li key={i} className="unit-slot">
                  {choices.length > 0 ? (
                    // Its loadouts, collapsed until opened.
                    <CardTextAccordion
                      label={description}
                      className="unit-slot__loadout"
                      expanded={openSlot === i}
                      onChange={(open) => setOpenSlot(open ? i : null)}
                    >
                      <ChoiceBoxes
                        label={`${name} loadout`}
                        options={choices.map((v) => ({
                          id: v.name,
                          label: variantLabel(loadout, v, name, itemNameOf),
                        }))}
                        value={current?.name}
                        onChange={(id) => changeLoadout(i, choices.find((v) => v.name === id))}
                      />
                    </CardTextAccordion>
                  ) : (
                    <span className="unit-slot__loadout">{description}</span>
                  )}
                  {!loadout.auto && <RemoveButton onClick={() => removeSlot(i)} />}
                </li>
              )
            })}
          </ul>
        )}

        {loadout.auto ? (
          <p className="hint">Nothing to choose: this unit is its one model, as equipped.</p>
        ) : full ? (
          <p className="hint">The unit is full. Remove a model to add a different one.</p>
        ) : (
          <>
            {composed ? (
              // A model the unit has room for, as equipped; its loadout is
              // picked once it's in the unit.
              <Field label="Add model to unit">
                <Select
                  options={addable.map((p) => ({
                    id: String(p.model_id),
                    name: `${modelName(p.model_id)} (${countOf(p.model_id)}/${p.max})`,
                  }))}
                  value={slot.model_id}
                  onChange={(id) => setSlot(composedSlot(partFor(loadout, id)))}
                  placeholder="Select model"
                />
              </Field>
            ) : (
              <>
                <Field label="Add model to unit">
                  <Select
                    options={datasheetModelOptions}
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
              </>
            )}
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
            <button
              type="button"
              disabled={!slot.model_id}
              onClick={addSlot}
            >
              Add Model
            </button>
          </>
        )}

        <button type="submit">{editingUnit ? 'Save Changes' : 'Add Unit'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default UnitFormPage
