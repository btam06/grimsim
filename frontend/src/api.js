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

export const listFactionUnits = () => request('/faction-units')
export const createFactionUnit = (payload) =>
  request('/faction-units', { method: 'POST', body: JSON.stringify(payload) })
export const deleteFactionUnit = (id) => request(`/faction-units/${id}`, { method: 'DELETE' })

export const listFactionAbilities = () => request('/faction-abilities')
export const createFactionAbility = (payload) =>
  request('/faction-abilities', { method: 'POST', body: JSON.stringify(payload) })
export const deleteFactionAbility = (id) =>
  request(`/faction-abilities/${id}`, { method: 'DELETE' })

export const listDispositions = () => request('/dispositions')
export const createDisposition = (payload) =>
  request('/dispositions', { method: 'POST', body: JSON.stringify(payload) })

export const listDetachments = () => request('/detachments')
export const createDetachment = (payload) =>
  request('/detachments', { method: 'POST', body: JSON.stringify(payload) })
export const deleteDetachment = (id) => request(`/detachments/${id}`, { method: 'DELETE' })
export const listDetachmentRules = () => request('/detachment-rules')
export const createDetachmentRule = (payload) =>
  request('/detachment-rules', { method: 'POST', body: JSON.stringify(payload) })
export const deleteDetachmentRule = (id) =>
  request(`/detachment-rules/${id}`, { method: 'DELETE' })

export const listStratagems = () => request('/stratagems')
// Stratagems usable on a unit as the 'attacker' or 'defender', in the
// shooting phase or (in engagement range) the fight phase.
// Positions worth asking about for a unit as the 'attacker' or 'defender'
// (e.g. within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit).
export const listGrantedAbilities = (unitId) =>
  request(`/combat/granted-abilities?unit_id=${unitId}`)
export const listRelevantPositions = (unitId, side) =>
  request(`/combat/positions?unit_id=${unitId}&side=${side}`)
export const listCalculatorStratagems = (unitId, side, inEngagementRange) =>
  request(
    `/combat/stratagems?unit_id=${unitId}&side=${side}&in_engagement_range=${inEngagementRange}`
  )
export const createStratagem = (payload) =>
  request('/stratagems', { method: 'POST', body: JSON.stringify(payload) })
export const deleteStratagem = (id) => request(`/stratagems/${id}`, { method: 'DELETE' })

export const listEnhancements = () => request('/enhancements')
export const createEnhancement = (payload) =>
  request('/enhancements', { method: 'POST', body: JSON.stringify(payload) })
export const deleteEnhancement = (id) => request(`/enhancements/${id}`, { method: 'DELETE' })
// Enhancements a model could carry in a unit of a list (unitId: the unit
// being edited, if any - its own enhancements still count as available).
// selectedRuleIds: detachment rules the unit is selected for (e.g. one giving
// CHARACTER), which can change what it can take.
const ruleParams = (selectedRuleIds = []) =>
  selectedRuleIds.map((id) => `&selected_rule_ids=${id}`).join('')
export const listAvailableEnhancements = (listId, modelId, unitId, selectedRuleIds) =>
  request(
    `/enhancements/available?list_id=${listId}&model_id=${modelId}` +
      (unitId ? `&unit_id=${unitId}` : '') +
      ruleParams(selectedRuleIds)
  )
// Upgrades a unit made of these models (one id per model) could take.
export const listAvailableUpgrades = (listId, modelIds, unitId, selectedRuleIds) =>
  request(
    `/enhancements/available-upgrades?list_id=${listId}` +
      modelIds.map((id) => `&model_ids=${id}`).join('') +
      (unitId ? `&unit_id=${unitId}` : '') +
      ruleParams(selectedRuleIds)
  )
// Detachment rules a unit made of these models could be selected for in its
// list (e.g. Houndpack Alphas), with how many other units already are.
export const listSelectableRules = (listId, modelIds, unitId) =>
  request(
    `/units/selectable-rules?list_id=${listId}` +
      modelIds.map((id) => `&model_ids=${id}`).join('') +
      (unitId ? `&unit_id=${unitId}` : '')
  )

export const listLists = () => request('/lists')
export const listBaseSizes = () => request('/base-sizes')
// The faction units and models a unit in this list can use.
export const listEligible = (listId) => request(`/lists/${listId}/eligible`)
export const createList = (payload) =>
  request('/lists', { method: 'POST', body: JSON.stringify(payload) })
export const updateList = (id, payload) =>
  request(`/lists/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteList = (id) => request(`/lists/${id}`, { method: 'DELETE' })

export const listKeywords = () => request('/keywords')
export const createKeyword = (payload) =>
  request('/keywords', { method: 'POST', body: JSON.stringify(payload) })
export const deleteKeyword = (id) => request(`/keywords/${id}`, { method: 'DELETE' })

export const listModels = () => request('/models')
export const createModel = (payload) =>
  request('/models', { method: 'POST', body: JSON.stringify(payload) })
export const updateModel = (id, payload) =>
  request(`/models/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const listWeapons = () => request('/weapons')
export const createWeapon = (payload) =>
  request('/weapons', { method: 'POST', body: JSON.stringify(payload) })
export const updateWeapon = (id, payload) =>
  request(`/weapons/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteWeapon = (id) => request(`/weapons/${id}`, { method: 'DELETE' })

export const listWargear = () => request('/wargear')
export const createWargear = (payload) =>
  request('/wargear', { method: 'POST', body: JSON.stringify(payload) })
export const updateWargear = (id, payload) =>
  request(`/wargear/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteWargear = (id) => request(`/wargear/${id}`, { method: 'DELETE' })

export const listUnits = () => request('/units')
export const createUnit = (payload) =>
  request('/units', { method: 'POST', body: JSON.stringify(payload) })
export const updateUnit = (id, payload) =>
  request(`/units/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteUnit = (id) => request(`/units/${id}`, { method: 'DELETE' })

export const runCombat = (payload) =>
  request('/combat', { method: 'POST', body: JSON.stringify(payload) })

export const listWeaponAbilities = () => request('/weapon-abilities')
export const createWeaponAbility = (payload) =>
  request('/weapon-abilities', { method: 'POST', body: JSON.stringify(payload) })

export const listWargearAbilities = () => request('/wargear-abilities')
export const createWargearAbility = (payload) =>
  request('/wargear-abilities', { method: 'POST', body: JSON.stringify(payload) })

export const listConditions = () => request('/conditions')
export const listEffects = () => request('/effects')

export const listDatasheetAbilities = () => request('/datasheet-abilities')
export const createDatasheetAbility = (payload) =>
  request('/datasheet-abilities', { method: 'POST', body: JSON.stringify(payload) })
export const updateDatasheetAbility = (id, payload) =>
  request(`/datasheet-abilities/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const attachDatasheetAbility = (modelId, abilityId) =>
  request(`/models/${modelId}/abilities/${abilityId}`, { method: 'PUT' })
export const detachDatasheetAbility = (modelId, abilityId) =>
  request(`/models/${modelId}/abilities/${abilityId}`, { method: 'DELETE' })

export const listUsers = () => request('/users')
export const createUser = (payload) =>
  request('/users', { method: 'POST', body: JSON.stringify(payload) })
export const deleteUser = (id) => request(`/users/${id}`, { method: 'DELETE' })

export const listSecondaryMissions = () => request('/secondary-missions')
export const createSecondaryMission = (payload) =>
  request('/secondary-missions', { method: 'POST', body: JSON.stringify(payload) })
export const deleteSecondaryMission = (id) =>
  request(`/secondary-missions/${id}`, { method: 'DELETE' })

export const listPrimaryMissions = () => request('/primary-missions')
export const createPrimaryMission = (payload) =>
  request('/primary-missions', { method: 'POST', body: JSON.stringify(payload) })
export const deletePrimaryMission = (id) =>
  request(`/primary-missions/${id}`, { method: 'DELETE' })

export const listGames = () => request('/games')
export const getGame = (id) => request(`/games/${id}`)
export const createGame = (payload) =>
  request('/games', { method: 'POST', body: JSON.stringify(payload) })
export const deleteGame = (id) => request(`/games/${id}`, { method: 'DELETE' })
export const startGame = (id) => request(`/games/${id}/start`, { method: 'POST' })
export const advanceGame = (id) => request(`/games/${id}/advance`, { method: 'POST' })
export const listUsableStratagems = (id, seat) => request(`/games/${id}/stratagems?seat=${seat}`)
export const playGameStratagem = (id, payload) =>
  request(`/games/${id}/stratagems`, { method: 'POST', body: JSON.stringify(payload) })
export const achieveSecondary = (id, cardId, points) =>
  request(`/games/${id}/secondaries/${cardId}/achieve`, {
    method: 'POST',
    body: JSON.stringify({ points }),
  })
export const discardSecondary = (id, cardId) =>
  request(`/games/${id}/secondaries/${cardId}/discard`, { method: 'POST' })
export const scorePrimary = (id, payload) =>
  request(`/games/${id}/primary-score`, { method: 'POST', body: JSON.stringify(payload) })
