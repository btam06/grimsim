// A datasheet's loadout (GET /faction-units/:id/loadout - its composition and
// wargear options, from the data) applied to the unit form's model slots.
// The server checks the same rules when the unit is saved
// (app/services/list_building/loadouts.py).

export const EMPTY_LOADOUT = {
  model_ids: [],
  composition: [],
  options: [],
  variants: [],
  auto: false,
}

export const partFor = (loadout, modelId) =>
  loadout.composition.find((p) => String(p.model_id) === String(modelId))

// A slot of a model as composed: what it starts with, no options taken.
export function composedSlot(part) {
  return {
    model_id: String(part.model_id),
    weapon_ids: part.weapon_ids,
    wargear_ids: part.wargear_ids,
    enhancement_id: '',
    options: [],
  }
}

// A slot of one of the datasheet's variants (a way to equip one of its models).
export const variantSlot = (variant) => ({
  model_id: String(variant.model_id),
  weapon_ids: variant.weapon_ids,
  wargear_ids: variant.wargear_ids,
  enhancement_id: '',
  options: variant.options,
})

// The unit's slots before anything is decided: the fewest of each model.
export const startingSlots = (loadout) =>
  loadout.composition.flatMap((part) => Array.from({ length: part.min }, () => composedSlot(part)))

const has = (slot, items) =>
  items.weapon_ids.every((id) => slot.weapon_ids.includes(id)) &&
  items.wargear_ids.every((id) => slot.wargear_ids.includes(id))

// Whether a slot has taken an option: as added, or - for a model already in
// the unit when it was opened - by having one of its choices beyond what the
// model starts with.
export function takes(slot, option, part) {
  if (String(option.model_id) !== slot.model_id) return false
  if (slot.options) return slot.options.includes(option.index)
  if (!part) return false
  return option.choices.some((c) => has(slot, c) && !has(part, c))
}

// How many models in a unit of `size` can take it (null: any).
export function limitOf(option, size) {
  if (option.max === null) return null
  return option.per ? option.max * Math.floor(size / option.per) : option.max
}

// Whether no more of the unit's models take each of these options than
// it allows.
function withinLimits(loadout, slots, optionIndexes) {
  return optionIndexes.every((index) => {
    const option = loadout.options.find((o) => o.index === index)
    const limit = limitOf(option, slots.length)
    const part = partFor(loadout, option.model_id)
    return limit === null || slots.filter((s) => takes(s, option, part)).length <= limit
  })
}

// The slots with one more of this model, as equipped, or null if the unit
// has all it can of it.
export function withModel(loadout, slots, part) {
  if (slots.filter((s) => s.model_id === String(part.model_id)).length >= part.max) return null
  return [...slots, composedSlot(part)]
}

const sameIds = (a, b) => a.length === b.length && [...a].sort().join() === [...b].sort().join()

// The variant a slot is equipped as (undefined: none of them).
export const variantOf = (loadout, slot) =>
  loadout.variants.find(
    (v) =>
      String(v.model_id) === slot.model_id &&
      sameIds(v.weapon_ids, slot.weapon_ids) &&
      sameIds(v.wargear_ids, slot.wargear_ids)
  )

// The slots with the one at `at` equipped as this variant instead (keeping
// its enhancement), or null if that'd take an option more often than allowed.
export function withSlotAs(loadout, slots, at, variant) {
  const next = slots.map((s, i) =>
    i === at ? { ...variantSlot(variant), enhancement_id: s.enhancement_id } : s
  )
  return withinLimits(loadout, next, variant.options) ? next : null
}

// What a model starts with that its options can replace - or, when they
// only add to it, all it starts with.
export function replaceable(loadout, part) {
  const options = loadout.options.filter((o) => String(o.model_id) === String(part.model_id))
  const replaced = (kind) =>
    part[kind].filter((id) => options.some((o) => o.replace[kind].includes(id)))
  const items = { weapon_ids: replaced('weapon_ids'), wargear_ids: replaced('wargear_ids') }
  return items.weapon_ids.length + items.wargear_ids.length > 0 ? items : part
}

// A weapon's or wargear's name without its profile ("Plasma caliver –
// standard" is the Plasma caliver), as the server matches them.
const itemName = (name) => name.split(/\s+[-–—]\s+/)[0].trim()

// A variant's name without its model's: "Arc rifle". The model as equipped
// is named by what it starts with that its options would replace
// ("Galvanic rifle"). `nameOf(kind, id)` names a weapon or wargear.
export function variantLabel(loadout, variant, modelName, nameOf) {
  const part = partFor(loadout, variant.model_id)
  if (variant.options.length === 0 && part) {
    const items = replaceable(loadout, part)
    const names = [
      ...items.weapon_ids.map((id) => nameOf('weapon', id)),
      ...items.wargear_ids.map((id) => nameOf('wargear', id)),
    ].map(itemName)
    if (names.length > 0) return [...new Set(names)].join(', ')
  }
  const prefix = `${modelName} — `
  const label = variant.name.startsWith(prefix) ? variant.name.slice(prefix.length) : variant.name
  return label.charAt(0).toUpperCase() + label.slice(1)
}

// The slots in order: the datasheet's sergeant first (the composition comes
// sergeant first), then its other models in composition order; for a
// free-form datasheet, a model the unit has just one of (among others)
// first. Otherwise as they were.
export function ordered(loadout, slots) {
  const rank = (slot) => {
    const at = loadout.composition.findIndex((p) => String(p.model_id) === slot.model_id)
    if (at !== -1) return at
    const count = slots.filter((s) => s.model_id === slot.model_id).length
    return loadout.composition.length + (count === 1 && slots.length > 1 ? 0 : 1)
  }
  return slots
    .map((slot, i) => [slot, i])
    .sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j)
    .map(([slot]) => slot)
}
