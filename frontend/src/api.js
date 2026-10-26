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
export const getTerrainLayout = (id) => request(`/terrain-layouts/${id}`)
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
export const getDeployment = (id) => request(`/games/${id}/deployment`)
export const getDeploymentFormation = (id, payload) =>
  request(`/games/${id}/deployment/formation`, { method: 'POST', body: JSON.stringify(payload) })
export const checkDeployment = (id, payload) =>
  request(`/games/${id}/deployment/check`, { method: 'POST', body: JSON.stringify(payload) })
export const getMovement = (id) => request(`/games/${id}/movement`)
export const rollAdvance = (id, payload) =>
  request(`/games/${id}/movement/advance`, { method: 'POST', body: JSON.stringify(payload) })
export const checkMove = (id, payload) =>
  request(`/games/${id}/movement/check`, { method: 'POST', body: JSON.stringify(payload) })
export const moveUnit = (id, payload) =>
  request(`/games/${id}/movement`, { method: 'POST', body: JSON.stringify(payload) })
export const resetMove = (id, payload) =>
  request(`/games/${id}/movement/reset`, { method: 'POST', body: JSON.stringify(payload) })
export const getShooting = (id) => request(`/games/${id}/shooting`)
export const getShootingTargets = (id, unitId) =>
  request(`/games/${id}/shooting/targets?unit_id=${unitId}`)
export const getShootingBubble = (id, unitId) =>
  request(`/games/${id}/shooting/bubble?unit_id=${unitId}`)
export const shoot = (id, payload) =>
  request(`/games/${id}/shooting`, { method: 'POST', body: JSON.stringify(payload) })
export const getReanimation = (id) => request(`/games/${id}/reanimation`)
export const checkReanimation = (id, payload) =>
  request(`/games/${id}/reanimation/check`, { method: 'POST', body: JSON.stringify(payload) })
export const placeReanimated = (id, payload) =>
  request(`/games/${id}/reanimation`, { method: 'POST', body: JSON.stringify(payload) })
export const getOverwatch = (id) => request(`/games/${id}/overwatch`)
export const getOverwatchTargets = (id, unitId) =>
  request(`/games/${id}/overwatch/targets?unit_id=${unitId}`)
export const fireOverwatch = (id, payload) =>
  request(`/games/${id}/overwatch`, { method: 'POST', body: JSON.stringify(payload) })
export const getCharge = (id) => request(`/games/${id}/charge`)
// An ability can let a unit re-roll its charge roll, once.
export const rerollCharge = (id, payload) =>
  request(`/games/${id}/charge/reroll`, { method: 'POST', body: JSON.stringify(payload) })
export const rollCharge = (id, payload) =>
  request(`/games/${id}/charge/roll`, { method: 'POST', body: JSON.stringify(payload) })
export const getChargeTargets = (id, unitId) =>
  request(`/games/${id}/charge/targets?unit_id=${unitId}`)
export const checkCharge = (id, payload) =>
  request(`/games/${id}/charge/check`, { method: 'POST', body: JSON.stringify(payload) })
export const makeCharge = (id, payload) =>
  request(`/games/${id}/charge`, { method: 'POST', body: JSON.stringify(payload) })
export const getPileIn = (id) => request(`/games/${id}/pile-in`)
export const checkPileIn = (id, payload) =>
  request(`/games/${id}/pile-in/check`, { method: 'POST', body: JSON.stringify(payload) })
export const pileIn = (id, payload) =>
  request(`/games/${id}/pile-in`, { method: 'POST', body: JSON.stringify(payload) })
export const finishPilingIn = (id, payload) =>
  request(`/games/${id}/pile-in/done`, { method: 'POST', body: JSON.stringify(payload) })
export const getFight = (id) => request(`/games/${id}/fight`)
export const getFightTargets = (id, unitId) =>
  request(`/games/${id}/fight/targets?unit_id=${unitId}`)
export const fight = (id, payload) =>
  request(`/games/${id}/fight`, { method: 'POST', body: JSON.stringify(payload) })
export const checkConsolidation = (id, payload) =>
  request(`/games/${id}/fight/consolidate/check`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const consolidate = (id, payload) =>
  request(`/games/${id}/fight/consolidate`, { method: 'POST', body: JSON.stringify(payload) })
export const skipConsolidation = (id, payload) =>
  request(`/games/${id}/fight/consolidate/skip`, { method: 'POST', body: JSON.stringify(payload) })
export const getMissionState = (id) => request(`/games/${id}/mission`)
export const answerMissionPrompt = (id, promptId, payload) =>
  request(`/games/${id}/mission/prompts/${promptId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const getActions = (id) => request(`/games/${id}/actions`)
export const startAction = (id, payload) =>
  request(`/games/${id}/actions`, { method: 'POST', body: JSON.stringify(payload) })
export const getScoring = (id) => request(`/games/${id}/scoring`)
export const claimOffer = (id, offerId) =>
  request(`/games/${id}/scoring/offers/${offerId}/claim`, { method: 'POST' })
export const holdOffer = (id, offerId) =>
  request(`/games/${id}/scoring/offers/${offerId}/hold`, { method: 'POST' })
export const getTurnRecord = (id) => request(`/games/${id}/turn-record`)
export const getBattleShock = (id) => request(`/games/${id}/battle-shock`)
export const requireBattleShockTest = (id, payload) =>
  request(`/games/${id}/battle-shock/test`, { method: 'POST', body: JSON.stringify(payload) })
export const takeBattleShockTest = (id, testId, insaneBravery) =>
  request(`/games/${id}/battle-shock/${testId}/take`, {
    method: 'POST',
    body: JSON.stringify({ insane_bravery: insaneBravery }),
  })
export const getCommand = (id) => request(`/games/${id}/command`)
export const chooseCommandOption = (id, payload) =>
  request(`/games/${id}/command/choice`, { method: 'POST', body: JSON.stringify(payload) })
export const getRoundStart = (id) => request(`/games/${id}/round-start`)
export const chooseRuleOption = (id, payload) =>
  request(`/games/${id}/round-start/choice`, { method: 'POST', body: JSON.stringify(payload) })
export const getReach = (id, payload) =>
  request(`/games/${id}/reach`, { method: 'POST', body: JSON.stringify(payload) })
export const getFormations = (id) => request(`/games/${id}/formations`)
export const setFormation = (id, payload) =>
  request(`/games/${id}/formations`, { method: 'POST', body: JSON.stringify(payload) })
export const declareFormations = (id, payload) =>
  request(`/games/${id}/formations/done`, { method: 'POST', body: JSON.stringify(payload) })
export const getEmbarked = (id) => request(`/games/${id}/embarked`)
export const getDisembarkFormation = (id, payload) =>
  request(`/games/${id}/embarked/formation`, { method: 'POST', body: JSON.stringify(payload) })
export const checkDisembark = (id, payload) =>
  request(`/games/${id}/embarked/check`, { method: 'POST', body: JSON.stringify(payload) })
export const disembark = (id, payload) =>
  request(`/games/${id}/embarked`, { method: 'POST', body: JSON.stringify(payload) })
export const getTeleportHomers = (id) => request(`/games/${id}/teleport-homers`)
export const placeTeleportHomer = (id, payload) =>
  request(`/games/${id}/teleport-homers`, { method: 'POST', body: JSON.stringify(payload) })
export const finishTeleportHomers = (id, payload) =>
  request(`/games/${id}/teleport-homers/done`, { method: 'POST', body: JSON.stringify(payload) })
export const getPsychic = (id) => request(`/games/${id}/psychic`)
export const castPsychic = (id, payload) =>
  request(`/games/${id}/psychic`, { method: 'POST', body: JSON.stringify(payload) })
export const getEmergency = (id) => request(`/games/${id}/emergency`)
export const checkEmergency = (id, payload) =>
  request(`/games/${id}/emergency/check`, { method: 'POST', body: JSON.stringify(payload) })
export const emergencyDisembark = (id, payload) =>
  request(`/games/${id}/emergency`, { method: 'POST', body: JSON.stringify(payload) })
export const embark = (id, payload) =>
  request(`/games/${id}/embarked/embark`, { method: 'POST', body: JSON.stringify(payload) })
export const getReserves = (id) => request(`/games/${id}/reserves`)
export const getReservesFormation = (id, payload) =>
  request(`/games/${id}/reserves/formation`, { method: 'POST', body: JSON.stringify(payload) })
export const checkArrival = (id, payload) =>
  request(`/games/${id}/reserves/check`, { method: 'POST', body: JSON.stringify(payload) })
export const bringIn = (id, payload) =>
  request(`/games/${id}/reserves`, { method: 'POST', body: JSON.stringify(payload) })
export const deployUnit = (id, payload) =>
  request(`/games/${id}/deployment`, { method: 'POST', body: JSON.stringify(payload) })
export const listUsableStratagems = (id, seat) => request(`/games/${id}/stratagems?seat=${seat}`)
export const playGameStratagem = (id, payload) =>
  request(`/games/${id}/stratagems`, { method: 'POST', body: JSON.stringify(payload) })
// The player's units a stratagem that targets one (e.g. Gunship Extraction)
// could be used on now: [{unit_id, name}].
export const listStratagemTargets = (id, stratagemId, seat) =>
  request(`/games/${id}/stratagems/${stratagemId}/targets?seat=${seat}`)
export const achieveSecondary = (id, cardId, points) =>
  request(`/games/${id}/secondaries/${cardId}/achieve`, {
    method: 'POST',
    body: JSON.stringify({ points }),
  })
export const discardSecondary = (id, cardId) =>
  request(`/games/${id}/secondaries/${cardId}/discard`, { method: 'POST' })
export const scorePrimary = (id, payload) =>
  request(`/games/${id}/primary-score`, { method: 'POST', body: JSON.stringify(payload) })
// Before the battle: the roll-off for who goes first, then Scouts moves (see
// app/services/in_game/first_turn.py and scouts.py).
export const rollFirstTurn = (id) => request(`/games/${id}/first-turn/roll`, { method: 'POST' })
export const getScouts = (id) => request(`/games/${id}/scouts`)
export const checkScoutMove = (id, payload) =>
  request(`/games/${id}/scouts/check`, { method: 'POST', body: JSON.stringify(payload) })
export const scoutMove = (id, payload) =>
  request(`/games/${id}/scouts`, { method: 'POST', body: JSON.stringify(payload) })
export const finishScouts = (id, payload) =>
  request(`/games/${id}/scouts/done`, { method: 'POST', body: JSON.stringify(payload) })
// Moving after shooting (e.g. Ride the Thermals - see
// app/services/in_game/shoot_scoot.py).
export const checkShootScoot = (id, payload) =>
  request(`/games/${id}/shoot-scoot/check`, { method: 'POST', body: JSON.stringify(payload) })
export const shootScoot = (id, payload) =>
  request(`/games/${id}/shoot-scoot`, { method: 'POST', body: JSON.stringify(payload) })
// The start of the Shooting phase (e.g. Secutor of Olympus - see
// app/services/in_game/shooting_start.py).
export const getShootingStart = (id) => request(`/games/${id}/shooting-start`)
export const applyShootingStart = (id, payload) =>
  request(`/games/${id}/shooting-start`, { method: 'POST', body: JSON.stringify(payload) })
// Reactive moves (e.g. Tactica Obliqua - see app/services/in_game/reactive_move.py).
export const listReactiveMoves = (id) => request(`/games/${id}/reactive-moves`)
export const rollReactiveMove = (id, payload) =>
  request(`/games/${id}/reactive-moves/roll`, { method: 'POST', body: JSON.stringify(payload) })
export const checkReactiveMove = (id, payload) =>
  request(`/games/${id}/reactive-moves/check`, { method: 'POST', body: JSON.stringify(payload) })
export const makeReactiveMove = (id, payload) =>
  request(`/games/${id}/reactive-moves`, { method: 'POST', body: JSON.stringify(payload) })
// Rallying a Battle-shocked unit (e.g. Servo-skull Uplink - see
// app/services/in_game/rally.py), and repairing a model in the Command phase
// (e.g. Omnissiah's Blessing - see repair.py).
export const listRallies = (id) => request(`/games/${id}/rallies`)
export const rallyUnit = (id, payload) =>
  request(`/games/${id}/rallies`, { method: 'POST', body: JSON.stringify(payload) })
export const listRepairs = (id) => request(`/games/${id}/repairs`)
export const repairModel = (id, payload) =>
  request(`/games/${id}/repairs`, { method: 'POST', body: JSON.stringify(payload) })
