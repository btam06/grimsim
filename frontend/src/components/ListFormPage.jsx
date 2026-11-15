import { useEffect, useState } from 'react'
import {
  createList,
  createUnit,
  deleteUnit,
  listBaseSizes,
  listDatasheetAbilities,
  listDispositions,
  listFactionAbilities,
  listWeaponAbilities,
  updateList,
} from '../api'
import DatasheetDialog from './DatasheetDialog'
import Field from './Field'
import Select from './Select'
import { CopyButton, DatasheetButton, DeleteButton, EditButton } from './IconButtons'
import { listPoints } from '../listPoints'

const POINTS_LIMIT_OPTIONS = [
  { id: '2000', name: '2000 points' },
  { id: '1000', name: '1000 points' },
]

function buildEmptyForm() {
  return {
    name: '',
    points_limit: '2000',
    faction_id: '',
    detachment_ids: [],
    user_id: '',
    warlord_unit_id: '',
    subfaction: '',
    disposition_id: '',
  }
}

function formFromList(list) {
  return {
    name: list.name,
    points_limit: String(list.points_limit),
    faction_id: String(list.faction_id),
    detachment_ids: list.detachment_ids,
    user_id: list.user_id === null ? '' : String(list.user_id),
    warlord_unit_id: list.warlord_unit_id === null ? '' : String(list.warlord_unit_id),
    subfaction: list.subfaction ?? '',
    disposition_id: list.disposition_id == null ? '' : String(list.disposition_id),
  }
}

function toPayload(form) {
  return {
    name: form.name,
    points_limit: Number(form.points_limit),
    faction_id: Number(form.faction_id),
    detachment_ids: form.detachment_ids,
    user_id: form.user_id === '' ? null : Number(form.user_id),
    warlord_unit_id: form.warlord_unit_id === '' ? null : Number(form.warlord_unit_id),
    subfaction: form.subfaction || null,
    disposition_id: form.disposition_id === '' ? null : Number(form.disposition_id),
  }
}

// Battlefield roles units are grouped under in the list builder, in order. A
// unit goes under the first one that every one of its models has - so a
// CHARACTER leading a unit sits with its bodyguard, not under Character.
const UNIT_CATEGORIES = [
  { label: 'Epic Hero', keyword: 'EPIC HERO' },
  { label: 'Character', keyword: 'CHARACTER' },
  { label: 'Battleline', keyword: 'BATTLELINE' },
  { label: 'Infantry', keyword: 'INFANTRY' },
  { label: 'Mounted', keyword: 'MOUNTED' },
  { label: 'Dedicated Transport', keyword: 'DEDICATED TRANSPORT' },
  { label: 'Monster', keyword: 'MONSTER' },
  { label: 'Vehicle', keyword: 'VEHICLE' },
]

function ListFormPage({
  editingList,
  users,
  factions,
  detachments,
  units,
  models,
  keywords,
  weapons,
  wargear,
  factionUnits,
  enhancements,
  detachmentRules = [],
  onSaved,
  onCancel,
  onUnitsChanged,
  onAddUnit,
  onEditUnit,
}) {
  const [form, setForm] = useState(editingList ? formFromList(editingList) : buildEmptyForm())
  const [error, setError] = useState(null)
  const [dispositions, setDispositions] = useState([])
  // The unit whose datasheet is open, and what's needed to show it (the
  // abilities and base sizes are fetched the first time one is opened).
  const [datasheetUnit, setDatasheetUnit] = useState(null)
  const [datasheetLookups, setDatasheetLookups] = useState(null)
  useEffect(() => {
    if (!datasheetUnit || datasheetLookups) return
    Promise.all([
      listWeaponAbilities(),
      listDatasheetAbilities(),
      listFactionAbilities(),
      listBaseSizes(),
    ])
      .then(([weaponAbilities, datasheetAbilities, factionAbilities, baseSizes]) =>
        setDatasheetLookups({ weaponAbilities, datasheetAbilities, factionAbilities, baseSizes })
      )
      .catch((err) => setError(err.message))
  }, [datasheetUnit, datasheetLookups])
  useEffect(() => {
    listDispositions()
      .then(setDispositions)
      .catch((err) => setError(err.message))
  }, [])
  // The dispositions the list's detachments offer - its games use the one
  // chosen (or the only one).
  const offeredDispositionIds = new Set(
    detachments
      .filter((d) => form.detachment_ids.includes(d.id))
      .flatMap((d) => d.disposition_ids ?? [])
  )
  const dispositionOptions = dispositions.filter((d) => offeredDispositionIds.has(d.id))

  const detachmentOptionsForFaction = detachments.filter(
    (d) => String(d.faction_id) === form.faction_id
  )
  const unitsInThisList = editingList ? units.filter((u) => u.list_id === editingList.id) : []

  // Keyword names every model in the unit has.
  const sharedKeywords = (unit) => {
    const perModel = unit.unit_models.map(
      (um) =>
        new Set(
          (models.find((m) => m.id === um.model_id)?.keyword_ids ?? []).map(
            (id) => keywords.find((k) => k.id === id)?.name
          )
        )
    )
    if (perModel.length === 0) return new Set()
    return new Set([...perModel[0]].filter((name) => perModel.every((set) => set.has(name))))
  }
  // Whether one of the unit's models is a CHARACTER (only those can be the
  // Warlord).
  // A CHARACTER: its models are, or a detachment rule it's selected for
  // makes it one (e.g. Houndpack Alphas' WAR DOG units).
  const characterId = keywords.find((k) => k.name === 'CHARACTER')?.id
  const isCharacter = (unit) =>
    unit.unit_models.some((um) =>
      (models.find((m) => m.id === um.model_id)?.keyword_ids ?? []).includes(characterId)
    ) ||
    (unit.selected_rule_ids ?? []).some((id) =>
      (detachmentRules.find((r) => r.id === id)?.granted_keyword_ids ?? []).includes(characterId)
    )
  const categoryOf = (unit) => {
    const shared = sharedKeywords(unit)
    return UNIT_CATEGORIES.find((c) => shared.has(c.keyword))?.label ?? 'Other'
  }
  // Only categories with units in them, in UNIT_CATEGORIES order, then Other.
  // Leader and support units attached to another of the list's units are
  // shown under it, not in their own category.
  const attachedTo = (unit) => unitsInThisList.filter((u) => u.attached_to_id === unit.id)
  const shownOnTheirOwn = unitsInThisList.filter(
    (u) => u.attached_to_id === null || !unitsInThisList.some((t) => t.id === u.attached_to_id)
  )
  const unitGroups = [...UNIT_CATEGORIES.map((c) => c.label), 'Other']
    .map((label) => ({ label, units: shownOnTheirOwn.filter((u) => categoryOf(u) === label) }))
    .filter((group) => group.units.length > 0)
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const factionUnitName = (id) => factionUnits.find((fu) => fu.id === id)?.name ?? `#${id}`
  // The open unit's datasheet shows its attached leaders' too, and its
  // bases by its points: each kind of model's, named by the model when they
  // differ.
  const datasheetAttached = datasheetUnit ? attachedTo(datasheetUnit) : []
  const datasheetBases = (() => {
    if (!datasheetUnit || !datasheetLookups) return ''
    const byModel = new Map()
    const unitModels = [datasheetUnit, ...datasheetAttached].flatMap((u) => u.unit_models)
    unitModels.forEach((um) => {
      const model = models.find((m) => m.id === um.model_id)
      const base = datasheetLookups.baseSizes.find((b) => b.id === model?.base_size_id)
      if (base) byModel.set(model.name, base.name)
    })
    const bases = [...new Set(byModel.values())]
    if (bases.length <= 1) return bases.length ? `${bases[0]} base` : ''
    return [...byModel].map(([model, base]) => `${base} base (${model})`).join(', ')
  })()
  const enhancementLabel = (id) => {
    const enhancement = enhancements.find((e) => e.id === id)
    return enhancement ? `${enhancement.name} (+${enhancement.points} pts)` : `#${id}`
  }
  // A unit's entry: its models, then the leader and support units attached
  // to it (each its own entry, under it).
  const renderUnit = (u) => (
    <li key={u.id}>
      {factionUnitName(u.faction_unit_id)}
      <DatasheetButton onClick={() => setDatasheetUnit(u)} /> — {u.points}pts
      {u.upgrade_id !== null && ` — Upgrade: ${enhancementLabel(u.upgrade_id)}`}
      {u.unit_models.length > 0 && (
        <ul>
          {u.unit_models.map((m) => (
            <li key={m.id}>
              {modelName(m.model_id)}
              {m.weapon_ids.length > 0 && ` — Weapons: ${m.weapon_ids.map(weaponName).join(', ')}`}
              {m.wargear_ids.length > 0 &&
                ` — Wargear: ${m.wargear_ids.map(wargearName).join(', ')}`}
              {m.enhancement_id !== null && ` — Enhancement: ${enhancementLabel(m.enhancement_id)}`}
            </li>
          ))}
        </ul>
      )}
      <EditButton onClick={() => onEditUnit(u)} />
      <CopyButton onClick={() => handleCopyUnit(u)} />
      <DeleteButton onClick={() => handleDeleteUnit(u.id)} />
      {attachedTo(u).length > 0 && (
        <div className="attached-units">
          <span className="hint">Attached:</span>
          <ul>{attachedTo(u).map(renderUnit)}</ul>
        </div>
      )}
    </li>
  )
  // The list's points: its units', plus their enhancements' and upgrades'.
  const totalPoints = listPoints(unitsInThisList, enhancements)
  const unitPoints = unitsInThisList.reduce((sum, u) => sum + u.points, 0)
  const extraPoints = totalPoints - unitPoints
  const pointsLimit = Number(form.points_limit)

  // What the faction's lists select, if anything (e.g. a Space Marines
  // Chapter).
  const selectedFaction = factions.find((f) => String(f.id) === form.faction_id)

  const handleFactionChange = (faction_id) => {
    setForm({ ...form, faction_id, detachment_ids: [], subfaction: '', disposition_id: '' })
  }

  const toggleDetachment = (id) => {
    const detachment_ids = form.detachment_ids.includes(id)
      ? form.detachment_ids.filter((d) => d !== id)
      : [...form.detachment_ids, id]
    // (Its disposition, if the detachments no longer offer it, goes.)
    const offered = new Set(
      detachments.filter((d) => detachment_ids.includes(d.id)).flatMap((d) => d.disposition_ids ?? [])
    )
    const disposition_id =
      form.disposition_id !== '' && !offered.has(Number(form.disposition_id))
        ? ''
        : form.disposition_id
    setForm({ ...form, detachment_ids, disposition_id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!form.faction_id) {
      setError('Faction is required')
      return
    }
    try {
      if (editingList) {
        await updateList(editingList.id, toPayload(form))
      } else {
        await createList(toPayload(form))
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  // Duplicates a unit - same datasheet, points and per-model loadout - into
  // this list, as a new unit that can then be edited on its own.
  const handleCopyUnit = async (unit) => {
    setError(null)
    try {
      await createUnit({
        faction_unit_id: unit.faction_unit_id,
        list_id: unit.list_id,
        unit_models: unit.unit_models.map((m) => ({
          model_id: m.model_id,
          weapon_ids: m.weapon_ids,
          wargear_ids: m.wargear_ids,
        })),
        // Enhancements and upgrades are once per list, so the copy has none.
      })
      onUnitsChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDeleteUnit = async (id) => {
    setError(null)
    try {
      await deleteUnit(id)
      onUnitsChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{editingList ? `Edit List #${editingList.id}` : 'Add List'}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </Field>
        <Field label="Owner">
          <Select
            options={[{ id: '', name: 'No owner' }, ...users]}
            value={form.user_id}
            onChange={(user_id) => setForm({ ...form, user_id })}
          />
        </Field>
        <Field label="Points Limit">
          <Select
            options={POINTS_LIMIT_OPTIONS}
            value={form.points_limit}
            onChange={(points_limit) => setForm({ ...form, points_limit })}
          />
        </Field>
        <Field label="Faction">
          <Select
            options={factions}
            value={form.faction_id}
            onChange={handleFactionChange}
            placeholder="Select faction"
          />
        </Field>
        {selectedFaction?.subfactions?.length > 0 && (
          <Field label={selectedFaction.subfaction_label}>
            <Select
              options={[
                { id: '', name: 'None' },
                ...selectedFaction.subfactions.map((name) => ({ id: name, name })),
              ]}
              value={form.subfaction}
              onChange={(subfaction) => setForm({ ...form, subfaction })}
            />
          </Field>
        )}
        {editingList && (
          // Its WARLORD: one of its CHARACTER units (checked when it's saved).
          <Field label="Warlord">
            <Select
              options={[
                { id: '', name: 'No Warlord' },
                ...unitsInThisList.filter(isCharacter).map((u) => ({
                  id: String(u.id),
                  name: `${factionUnitName(u.faction_unit_id)} — ${u.points}pts`,
                })),
              ]}
              value={form.warlord_unit_id}
              onChange={(warlord_unit_id) => setForm({ ...form, warlord_unit_id })}
            />
          </Field>
        )}
        <div className="checkbox-group">
          Detachments
          {detachmentOptionsForFaction.length === 0 && (
            <p className="hint">Select a faction to see its detachments</p>
          )}
          <div className="checkbox-grid">
            {detachmentOptionsForFaction.map((d) => (
              <label key={d.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={form.detachment_ids.includes(d.id)}
                  onChange={() => toggleDetachment(d.id)}
                />
                {d.name} (DP {d.dp})
              </label>
            ))}
          </div>
        </div>
        {dispositionOptions.length > 0 && (
          // Its disposition: one its detachments offer (games use it).
          <Field label="Disposition">
            <Select
              options={[
                {
                  id: '',
                  name: dispositionOptions.length === 1 ? dispositionOptions[0].name : 'Choose one',
                },
                ...(dispositionOptions.length > 1 ? dispositionOptions : []),
              ]}
              value={dispositionOptions.length === 1 ? '' : form.disposition_id}
              onChange={(disposition_id) => setForm({ ...form, disposition_id })}
              isDisabled={dispositionOptions.length === 1}
            />
          </Field>
        )}
        <button type="submit">{editingList ? 'Save Changes' : 'Add List'}</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>

      {editingList && (
        <>
          <h3>Units</h3>
          <p className={totalPoints > pointsLimit ? 'error' : 'game-totals'}>
            <strong>{totalPoints}</strong> / {pointsLimit} pts
            {extraPoints > 0 && (
              <span className="hint">
                {' '}
                ({unitPoints} units + {extraPoints} enhancements and upgrades)
              </span>
            )}
            {totalPoints > pointsLimit && ` — ${totalPoints - pointsLimit} pts over`}
          </p>
          <button type="button" onClick={() => onAddUnit(editingList.id)}>
            + Add Unit
          </button>
          {unitGroups.map((group) => (
            <div key={group.label}>
              <h4>{group.label}</h4>
              <ul>{group.units.map(renderUnit)}</ul>
            </div>
          ))}
        </>
      )}
      <DatasheetDialog
        unit={datasheetUnit && datasheetLookups ? datasheetUnit : null}
        title={
          datasheetUnit &&
          `${factionUnitName(datasheetUnit.faction_unit_id)} — ${datasheetUnit.points}pts` +
            (datasheetBases ? ` · ${datasheetBases}` : '')
        }
        data={{ models, weapons, wargear, keywords, enhancements, ...datasheetLookups }}
        attached={datasheetAttached.map((a) => ({
          unit: a,
          title: `${factionUnitName(a.faction_unit_id)} — ${a.points}pts (attached)`,
        }))}
        onClose={() => setDatasheetUnit(null)}
      />
    </section>
  )
}

export default ListFormPage
