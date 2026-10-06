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
  if (response.status === 204) return null
  return response.json()
}

export const listFactions = () => request('/factions')
export const createFaction = (payload) =>
  request('/factions', { method: 'POST', body: JSON.stringify(payload) })
export const deleteFaction = (id) => request(`/factions/${id}`, { method: 'DELETE' })

export const listDispositions = () => request('/dispositions')
export const createDisposition = (payload) =>
  request('/dispositions', { method: 'POST', body: JSON.stringify(payload) })

export const listDetachments = () => request('/detachments')
export const createDetachment = (payload) =>
  request('/detachments', { method: 'POST', body: JSON.stringify(payload) })
export const deleteDetachment = (id) => request(`/detachments/${id}`, { method: 'DELETE' })

export const listLists = () => request('/lists')
export const createList = (payload) =>
  request('/lists', { method: 'POST', body: JSON.stringify(payload) })
export const updateList = (id, payload) =>
  request(`/lists/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const listModels = () => request('/models')
export const createModel = (payload) =>
  request('/models', { method: 'POST', body: JSON.stringify(payload) })
export const updateModel = (id, payload) =>
  request(`/models/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const listWeapons = () => request('/weapons')
export const createWeapon = (payload) =>
  request('/weapons', { method: 'POST', body: JSON.stringify(payload) })

export const listWargear = () => request('/wargear')
export const createWargear = (payload) =>
  request('/wargear', { method: 'POST', body: JSON.stringify(payload) })

export const listUnits = () => request('/units')
export const createUnit = (payload) =>
  request('/units', { method: 'POST', body: JSON.stringify(payload) })
export const deleteUnit = (id) => request(`/units/${id}`, { method: 'DELETE' })

export const listWeaponAbilities = () => request('/weapon-abilities')
export const createWeaponAbility = (payload) =>
  request('/weapon-abilities', { method: 'POST', body: JSON.stringify(payload) })

export const listDatasheetAbilities = () => request('/datasheet-abilities')
export const createDatasheetAbility = (payload) =>
  request('/datasheet-abilities', { method: 'POST', body: JSON.stringify(payload) })
