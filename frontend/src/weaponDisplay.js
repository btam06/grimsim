export function skillLabel(weaponType) {
  if (weaponType === 'melee') return 'WS'
  if (weaponType === 'ranged') return 'BS'
  return 'WS/BS'
}
