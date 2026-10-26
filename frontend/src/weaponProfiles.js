// Weapons with several profiles (e.g. "Plasma caliver – standard" and
// "Plasma caliver – supercharge", or "– strike" and "– sweep"): each profile
// is named "<weapon> – <profile>" - or its usual one sometimes just
// "<weapon>" (e.g. "Melta Rifle" and "Melta Rifle - Hunter") - and a model
// attacks with only one profile of a weapon at a time (see
// app/services/weapon_profiles.py, which checks).

const SEPARATOR = /\s+[-–—]\s+/

// The weapon a profile belongs to, or null if it isn't one of several.
export function profileGroup(name) {
  const parts = (name ?? '').split(SEPARATOR)
  return parts.length > 1 ? parts[0] : null
}

// The items (weapons, or anything with a name via `nameOf`) less any other
// profile of the same weapon as the first-come one of each - for picking
// every weapon at once.
export function onePerProfile(items, nameOf = (item) => item.name) {
  const seen = new Map()
  return items.filter((item) => {
    // (A weapon that isn't one of several profiles is its own group.)
    const group = profileGroup(nameOf(item)) ?? nameOf(item)
    const first = seen.get(group)
    if (first === undefined) {
      seen.set(group, nameOf(item))
      return true
    }
    // The same profile again (e.g. on another model) still counts.
    return first === nameOf(item)
  })
}

// Whether two names are different profiles of the same weapon.
export function otherProfile(a, b) {
  return a !== b && (profileGroup(a) ?? a) === (profileGroup(b) ?? b)
}
