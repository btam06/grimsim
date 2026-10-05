const BASE = '/api'

async function request(path, options) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${response.status}`)
  }
  return response.json()
}

export const listModels = () => request('/models')
export const createModel = (payload) =>
  request('/models', { method: 'POST', body: JSON.stringify(payload) })

export const listUnits = () => request('/units')
export const createUnit = (payload) =>
  request('/units', { method: 'POST', body: JSON.stringify(payload) })

export const listWeaponAbilities = () => request('/weapon-abilities')
export const createWeaponAbility = (payload) =>
  request('/weapon-abilities', { method: 'POST', body: JSON.stringify(payload) })

export const listDatasheetAbilities = () => request('/datasheet-abilities')
export const createDatasheetAbility = (payload) =>
  request('/datasheet-abilities', { method: 'POST', body: JSON.stringify(payload) })
