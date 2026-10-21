export function skillLabel(weaponType) {
  if (weaponType === 'melee') return 'WS'
  if (weaponType === 'ranged') return 'BS'
  return 'WS/BS'
}

// A weapon's BS/WS for display: "3+", or "N/A" for one that doesn't roll to
// hit (stored as 0, e.g. a [TORRENT] weapon).
export function skillValue(skill) {
  return skill ? `${skill}+` : 'N/A'
}
