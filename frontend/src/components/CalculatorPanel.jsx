import { faArrowRightArrowLeft } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { useEffect, useMemo, useState } from 'react'
import {
  listDatasheetAbilities,
  listEffects,
  listBaseSizes,
  listEnhancements,
  listKeywords,
  listWargear,
  listFactionAbilities,
  listFactionUnits,
  listLists,
  listModels,
  listCalculatorStratagems,
  listGrantedAbilities,
  listRelevantPositions,
  listUnits,
  listWeaponAbilities,
  listWeapons,
  runCombat,
} from '../api'
import Field from './Field'
import { Described, RuleOptionPicker } from './RuleOptionPicker'
import CombatResults from './CombatResults'
import Select from './Select'
import UnitDatasheet from './UnitDatasheet'

// The stratagems usable on a unit as the 'attacker' or 'defender', from the
// server, for the shooting phase (ranged) or the fight phase (melee).
// Switching phase or unit drops any selection that's no longer usable.
function useUsableStratagems(unitId, side, inEngagementRange, setSelected, onError) {
  const [available, setAvailable] = useState([])
  useEffect(() => {
    if (!unitId) {
      setAvailable([])
      return
    }
    let cancelled = false
    listCalculatorStratagems(unitId, side, inEngagementRange)
      .then((stratagems) => {
        if (cancelled) return
        setAvailable(stratagems)
        const ids = new Set(stratagems.map((st) => st.id))
        setSelected((selected) => selected.filter((id) => ids.has(id)))
      })
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId, side, inEngagementRange])
  return available
}

// The positions worth asking about for a unit as the 'attacker' or 'defender'
// - only those its rules read - from the server. Changing the unit clears
// the ones ticked.
function useRelevantPositions(unitId, side, setSelected, onError) {
  const [available, setAvailable] = useState([])
  useEffect(() => {
    setSelected([])
    if (!unitId) {
      setAvailable([])
      return
    }
    let cancelled = false
    listRelevantPositions(unitId, side)
      .then((positions) => !cancelled && setAvailable(positions))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId, side])
  return available
}

// The ids of the datasheet abilities a unit gains from its enhancements and
// its list's detachment rules (e.g. Malefic Surge), from the server - so their
// options can be offered too.
function useGrantedAbilities(unitId, onError) {
  const [granted, setGranted] = useState([])
  useEffect(() => {
    if (!unitId) {
      setGranted([])
      return
    }
    let cancelled = false
    listGrantedAbilities(unitId)
      .then((ids) => !cancelled && setGranted(ids))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId])
  return granted
}

// One side's positions, as a column headed by the side.
function PositionPicker({ side, positions, selectedIds, onChange }) {
  const toggle = (id) =>
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id])
  return (
    <div className="checkbox-group">
      {side}
      {positions.length === 0 && <p className="hint">None</p>}
      {positions.map((p) => (
        <label key={p.id} className="checkbox-field">
          <input
            type="checkbox"
            checked={selectedIds.includes(p.id)}
            onChange={() => toggle(p.id)}
          />
          {p.label}
        </label>
      ))}
    </div>
  )
}

function StratagemPicker({ side, stratagems, selectedIds, onChange }) {
  const toggle = (id) =>
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id])
  return (
    <div className="checkbox-group">
      {side}
      {stratagems.length === 0 && <p className="hint">None usable in this phase</p>}
      <div className="checkbox-grid">
        {stratagems.map((s) => (
          <label key={s.id} className="checkbox-field">
            <input
              type="checkbox"
              checked={selectedIds.includes(s.id)}
              onChange={() => toggle(s.id)}
            />
            <Described description={s.description}>
              {s.name} ({s.cp} CP{s.is_core ? ', Core' : ''})
            </Described>
          </label>
        ))}
      </div>
    </div>
  )
}

function CalculatorPanel() {
  const [units, setUnits] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [weapons, setWeapons] = useState([])
  const [enhancements, setEnhancements] = useState([])
  const [lists, setLists] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [effects, setEffects] = useState([])
  const [models, setModels] = useState([])
  const [factionAbilities, setFactionAbilities] = useState([])
  const [datasheetAbilities, setDatasheetAbilities] = useState([])
  // For the units' datasheets.
  const [keywords, setKeywords] = useState([])
  const [wargear, setWargear] = useState([])
  const [baseSizes, setBaseSizes] = useState([])
  // {faction ability id: selected rule option name ('' for none)}, per side.
  const [attackerRuleChoices, setAttackerRuleChoices] = useState({})
  const [defenderRuleChoices, setDefenderRuleChoices] = useState({})
  // Each side picks a list, then one of that list's units.
  const [attackingListId, setAttackingListId] = useState('')
  const [defendingListId, setDefendingListId] = useState('')
  const [attackingUnitId, setAttackingUnitId] = useState('')
  const [defendingUnitId, setDefendingUnitId] = useState('')
  const [inEngagementRange, setInEngagementRange] = useState(false)
  const [inCover, setInCover] = useState(false)
  const [halfRange, setHalfRange] = useState(false)
  const [movedLessThan3, setMovedLessThan3] = useState(false)
  const [charged, setCharged] = useState(false)
  const [defenderBattleShocked, setDefenderBattleShocked] = useState(false)
  const [attackerDamaged, setAttackerDamaged] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [selectedWeaponNames, setSelectedWeaponNames] = useState([])
  const [selectedStratagemIds, setSelectedStratagemIds] = useState([])
  const [selectedDefenderStratagemIds, setSelectedDefenderStratagemIds] = useState([])
  const [attackerPositionIds, setAttackerPositionIds] = useState([])
  const [defenderPositionIds, setDefenderPositionIds] = useState([])
  const [applyPrecision, setApplyPrecision] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Results are for the options they were calculated with, so changing any
  // option clears them.
  useEffect(() => {
    setResult(null)
  }, [
    attackerRuleChoices,
    defenderRuleChoices,
    attackingListId,
    defendingListId,
    attackingUnitId,
    defendingUnitId,
    inEngagementRange,
    inCover,
    halfRange,
    movedLessThan3,
    charged,
    defenderBattleShocked,
    attackerDamaged,
    advanced,
    selectedWeaponNames,
    selectedStratagemIds,
    selectedDefenderStratagemIds,
    attackerPositionIds,
    defenderPositionIds,
    applyPrecision,
  ])

  useEffect(() => {
    listUnits().then(setUnits).catch((err) => setError(err.message))
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
    listEnhancements().then(setEnhancements).catch((err) => setError(err.message))
    listLists().then(setLists).catch((err) => setError(err.message))
    listWeaponAbilities().then(setWeaponAbilities).catch((err) => setError(err.message))
    listEffects().then(setEffects).catch((err) => setError(err.message))
    listModels().then(setModels).catch((err) => setError(err.message))
    listFactionAbilities().then(setFactionAbilities).catch((err) => setError(err.message))
    listDatasheetAbilities().then(setDatasheetAbilities).catch((err) => setError(err.message))
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
    listWargear().then(setWargear).catch((err) => setError(err.message))
    listBaseSizes().then(setBaseSizes).catch((err) => setError(err.message))
  }, [])

  const unitLabel = (unit) => {
    const name = factionUnits.find((fu) => fu.id === unit.faction_unit_id)?.name ?? `#${unit.faction_unit_id}`
    return `${name} (unit #${unit.id})`
  }

  const unitOptionsFor = (listId) =>
    units
      .filter((u) => listId !== '' && u.list_id === Number(listId))
      .map((u) => ({ id: u.id, name: unitLabel(u) }))

  // Changing a side's list keeps its unit only if that unit is in the new list.
  const selectList = (listId, unitId, setListId, setUnitId) => {
    setListId(listId)
    const unit = units.find((u) => u.id === Number(unitId))
    if (!unit || unit.list_id !== Number(listId)) setUnitId('')
  }

  const swapSides = () => {
    setAttackingListId(defendingListId)
    setDefendingListId(attackingListId)
    setAttackingUnitId(defendingUnitId)
    setDefendingUnitId(attackingUnitId)
  }

  const attackingUnit = units.find((u) => u.id === Number(attackingUnitId))

  // Weapons sharing a name (e.g. one per model in a 5-model squad) are
  // grouped into a single checklist entry - checking it selects every
  // underlying weapon id in the group.
  // Weapons the attacking unit's enhancements give it (e.g. TL-4Ø9), shaped
  // like weapons, with ids like "enh-7" (sent as selected_enhancement_weapon_ids).
  const enhancementWeapons = useMemo(() => {
    if (!attackingUnit) return []
    return attackingUnit.unit_models.flatMap((um) =>
      (enhancements.find((e) => e.id === um.enhancement_id)?.weapons ?? []).map((w) => ({
        ...w,
        id: `enh-${w.id}`,
        enhancementWeaponId: w.id,
      }))
    )
  }, [attackingUnit, enhancements])
  const knownWeapons = useMemo(
    () => [...weapons, ...enhancementWeapons],
    [weapons, enhancementWeapons]
  )

  const weaponGroups = useMemo(() => {
    if (!attackingUnit) return []
    const weaponIds = [
      ...attackingUnit.unit_models.flatMap((um) => um.weapon_ids),
      ...enhancementWeapons.map((w) => w.id),
    ]
    const groups = new Map()
    weaponIds.forEach((id) => {
      const weapon = knownWeapons.find((w) => w.id === id)
      if (!weapon) return
      if (!groups.has(weapon.name)) groups.set(weapon.name, [])
      groups.get(weapon.name).push(id)
    })
    return Array.from(groups.entries()).map(([name, ids]) => ({ name, weaponIds: ids }))
  }, [attackingUnit, knownWeapons, enhancementWeapons])

  // Only the weapons usable in the chosen engagement: ranged weapons when
  // shooting; melee weapons in engagement range, plus Pistols (which can
  // still shoot there).
  const visibleWeaponGroups = useMemo(() => {
    const pistolEffectId = effects.find((e) => e.keyword === 'pistol')?.id
    const pistolAbilityIds = new Set(
      weaponAbilities.filter((a) => a.effect_ids.includes(pistolEffectId)).map((a) => a.id)
    )
    return weaponGroups
      .map((g) => {
        const weapon = knownWeapons.find((w) => w.id === g.weaponIds[0])
        const isMelee = weapon?.weapon_type === 'melee'
        const isPistol = !isMelee && weapon?.ability_ids.some((id) => pistolAbilityIds.has(id))
        return { ...g, isMelee, isPistol }
      })
      .filter((g) => (inEngagementRange ? g.isMelee || g.isPistol : !g.isMelee))
  }, [weaponGroups, knownWeapons, weaponAbilities, effects, inEngagementRange])

  // Default every weapon group to selected whenever the attacking unit
  // changes (or its weapons finish loading).
  useEffect(() => {
    setSelectedWeaponNames(weaponGroups.map((g) => g.name))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attackingUnitId, weapons, enhancementWeapons])

  // Stratagems are opt-in, so clear them whenever that side's unit changes.
  useEffect(() => {
    setSelectedStratagemIds([])
  }, [attackingUnitId])

  useEffect(() => {
    setSelectedDefenderStratagemIds([])
  }, [defendingUnitId])

  const attackerStratagems = useUsableStratagems(
    attackingUnitId,
    'attacker',
    inEngagementRange,
    setSelectedStratagemIds,
    setError
  )
  const attackerPositions = useRelevantPositions(
    attackingUnitId,
    'attacker',
    setAttackerPositionIds,
    setError
  )
  const defenderPositions = useRelevantPositions(
    defendingUnitId,
    'defender',
    setDefenderPositionIds,
    setError
  )
  const attackerGrantedAbilityIds = useGrantedAbilities(attackingUnitId, setError)
  const defenderGrantedAbilityIds = useGrantedAbilities(defendingUnitId, setError)
  const defenderStratagems = useUsableStratagems(
    defendingUnitId,
    'defender',
    inEngagementRange,
    setSelectedDefenderStratagemIds,
    setError
  )

  // Abilities with rule options a unit can pick from, as {key, name,
  // rule_options}:
  // - faction abilities (e.g. Doctrina Imperatives) any of its models has;
  // - datasheet abilities (e.g. Belisarius Cawl's Canticles of the Omnissiah)
  //   any of its models has, or any model in another unit of the same faction
  //   in its army list has - the server applies only the options that reach
  //   that far;
  // - datasheet abilities its enhancements or detachment rules give it
  //   (grantedIds).
  const ruleAbilitiesFor = (unit, grantedIds) => {
    if (!unit) return []
    const modelsIn = (u) =>
      u.unit_models.map((um) => models.find((m) => m.id === um.model_id)).filter(Boolean)
    const factionOf = (u) => factionUnits.find((fu) => fu.id === u.faction_unit_id)?.faction_id

    const heldFactionIds = new Set(modelsIn(unit).flatMap((m) => m.faction_ability_ids))
    const entries = factionAbilities
      .filter((a) => heldFactionIds.has(a.id) && a.rule_options.length > 0)
      .map((a) => ({
        key: `faction-${a.id}`,
        name: a.name,
        description: a.description,
        rule_options: a.rule_options,
        option_descriptions: a.rule_option_descriptions,
        required: a.required,
      }))

    const armyUnits =
      unit.list_id === null
        ? [unit]
        : units.filter(
            (u) =>
              u.id === unit.id || (u.list_id === unit.list_id && factionOf(u) === factionOf(unit))
          )
    const seen = new Set()
    armyUnits.flatMap(modelsIn).forEach((model) => {
      model.ability_ids.forEach((id) => {
        const ability = datasheetAbilities.find((a) => a.id === id)
        if (!ability || ability.rule_options.length === 0 || seen.has(id)) return
        seen.add(id)
        entries.push({
          key: `datasheet-${id}`,
          name: `${ability.name} (${model.name})`,
          description: ability.description,
          rule_options: ability.rule_options,
          option_descriptions: ability.rule_option_descriptions,
        })
      })
    })
    grantedIds.forEach((id) => {
      const ability = datasheetAbilities.find((a) => a.id === id)
      if (!ability || ability.rule_options.length === 0 || seen.has(id)) return
      seen.add(id)
      entries.push({
        key: `datasheet-${id}`,
        name: ability.name,
        description: ability.description,
        rule_options: ability.rule_options,
        option_descriptions: ability.rule_option_descriptions,
      })
    })
    return entries
  }
  const defendingUnit = units.find((u) => u.id === Number(defendingUnitId))
  const datasheetData = {
    models,
    weapons,
    wargear,
    weaponAbilities,
    datasheetAbilities,
    factionAbilities,
    keywords,
    baseSizes,
    enhancements,
  }
  const attackerRuleAbilities = ruleAbilitiesFor(attackingUnit, attackerGrantedAbilityIds)
  const defenderRuleAbilities = ruleAbilitiesFor(defendingUnit, defenderGrantedAbilityIds)

  useEffect(() => {
    setAttackerRuleChoices({})
  }, [attackingUnitId])

  useEffect(() => {
    setDefenderRuleChoices({})
  }, [defendingUnitId])

  // What's picked for each ability the unit has - and, for one whose options
  // are required (e.g. Doctrina Imperatives), its first option until another's
  // picked.
  const effectiveChoices = (abilities, choices) =>
    Object.fromEntries(
      abilities.map((a) => [
        a.key,
        choices[a.key] || (a.required ? a.rule_options[0] : ''),
      ])
    )

  // Only send choices for abilities the unit currently has.
  const selectedRuleOptions = (abilities, choices) =>
    Object.values(effectiveChoices(abilities, choices)).filter(Boolean)

  // Precision is only worth offering when something about to attack has the
  // precision effect - a selected weapon's ability, or a selected stratagem.
  const hasPrecision = useMemo(() => {
    const precisionEffectId = effects.find((e) => e.keyword === 'precision')?.id
    if (precisionEffectId === undefined) return false
    const precisionAbilityIds = new Set(
      weaponAbilities.filter((a) => a.effect_ids.includes(precisionEffectId)).map((a) => a.id)
    )
    const weaponHasPrecision = visibleWeaponGroups
      .filter((g) => selectedWeaponNames.includes(g.name))
      .flatMap((g) => g.weaponIds)
      .some((id) =>
        knownWeapons
          .find((w) => w.id === id)
          ?.ability_ids.some((aid) => precisionAbilityIds.has(aid))
      )
    const stratagemHasPrecision = attackerStratagems.some(
      (s) => selectedStratagemIds.includes(s.id) && s.effect_ids.includes(precisionEffectId)
    )
    return weaponHasPrecision || stratagemHasPrecision
  }, [
    effects,
    weaponAbilities,
    visibleWeaponGroups,
    selectedWeaponNames,
    knownWeapons,
    attackerStratagems,
    selectedStratagemIds,
  ])


  const toggleWeaponName = (name) => {
    setSelectedWeaponNames((names) =>
      names.includes(name) ? names.filter((n) => n !== name) : [...names, name]
    )
  }

  const handleCalculate = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    if (!attackingUnitId || !defendingUnitId) {
      setError('Attacking and defending units are required')
      return
    }
    try {
      const selectedWeaponIds = visibleWeaponGroups
        .filter((g) => selectedWeaponNames.includes(g.name))
        .flatMap((g) => g.weaponIds)
      const response = await runCombat({
        attacking_unit_id: Number(attackingUnitId),
        defending_unit_id: Number(defendingUnitId),
        selected_weapon_ids: selectedWeaponIds.filter((id) => typeof id === 'number'),
        selected_enhancement_weapon_ids: selectedWeaponIds
          .map((id) => knownWeapons.find((w) => w.id === id)?.enhancementWeaponId)
          .filter((id) => id !== undefined),
        stratagem_ids: selectedStratagemIds,
        defender_stratagem_ids: selectedDefenderStratagemIds,
        attacker_positions: attackerPositionIds,
        defender_positions: defenderPositionIds,
        apply_precision: hasPrecision && applyPrecision,
        attacker_rule_options: selectedRuleOptions(attackerRuleAbilities, attackerRuleChoices),
        defender_rule_options: selectedRuleOptions(defenderRuleAbilities, defenderRuleChoices),
        in_engagement_range: inEngagementRange,
        in_cover: inCover,
        half_range: halfRange,
        moved_less_than_3: movedLessThan3,
        charged: inEngagementRange && charged,
        defender_battle_shocked: defenderBattleShocked,
        attacker_damaged: attackerDamaged,
        advanced,
      })
      // Feel no pain rolls are only worth showing if the defender has FNP -
      // its own, or granted by a rule (e.g. a leader), which shows up as FNP
      // rolls having been made. Captured now, so changing the defender
      // afterwards doesn't affect it.
      const defenderHasFnp =
        response.fnp_rolls.length > 0 ||
        (defendingUnit?.unit_models ?? []).some(
          (um) => models.find((m) => m.id === um.model_id)?.feel_no_pain != null
        )
      setResult({ ...response, defenderHasFnp })
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Calculator</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleCalculate}>
        <div className="matchup">
          <fieldset className="form-section matchup-side">
            <legend>Attacker</legend>
            <Field label="List">
              <Select
                options={lists}
                value={attackingListId}
                onChange={(listId) =>
                  selectList(listId, attackingUnitId, setAttackingListId, setAttackingUnitId)
                }
                placeholder="Select attacking list"
              />
            </Field>
            <Field label="Unit">
              <Select
                options={unitOptionsFor(attackingListId)}
                value={attackingUnitId}
                onChange={setAttackingUnitId}
                placeholder={attackingListId ? 'Select attacking unit' : 'Select a list first'}
              />
            </Field>
            <UnitDatasheet unit={attackingUnit} data={datasheetData} />
          </fieldset>
          <button
            type="button"
            className="swap-button"
            onClick={swapSides}
            title="Swap attacker and defender"
            aria-label="Swap attacker and defender"
          >
            <FontAwesomeIcon icon={faArrowRightArrowLeft} />
          </button>
          <fieldset className="form-section matchup-side">
            <legend>Defender</legend>
            <Field label="List">
              <Select
                options={lists}
                value={defendingListId}
                onChange={(listId) =>
                  selectList(listId, defendingUnitId, setDefendingListId, setDefendingUnitId)
                }
                placeholder="Select defending list"
              />
            </Field>
            <Field label="Unit">
              <Select
                options={unitOptionsFor(defendingListId)}
                value={defendingUnitId}
                onChange={setDefendingUnitId}
                placeholder={defendingListId ? 'Select defending unit' : 'Select a list first'}
              />
            </Field>
            <UnitDatasheet unit={defendingUnit} data={datasheetData} />
          </fieldset>
        </div>
        <fieldset className="form-section">
          <legend>Engagement</legend>
          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="in_engagement_range"
                checked={!inEngagementRange}
                onChange={() => setInEngagementRange(false)}
              />
              Ranged
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="in_engagement_range"
                checked={inEngagementRange}
                onChange={() => setInEngagementRange(true)}
              />
              Melee (in engagement range)
            </label>
          </div>
        </fieldset>
        {visibleWeaponGroups.length > 0 && (
          <fieldset className="form-section">
            <legend>{inEngagementRange ? 'Weapons to Fight With' : 'Weapons to Shoot'}</legend>
            <div className="checkbox-grid">
              {visibleWeaponGroups.map((g) => (
                <label key={g.name} className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={selectedWeaponNames.includes(g.name)}
                    onChange={() => toggleWeaponName(g.name)}
                  />
                  {g.name}
                  {g.isPistol && ' (Pistol)'}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {(attackingUnit || defendingUnit) && (
          <fieldset className="form-section">
            <legend>
              Stratagems ({inEngagementRange ? 'Fight' : 'Shooting'} Phase)
            </legend>
            <StratagemPicker
              side="Attacker"
              stratagems={attackerStratagems}
              selectedIds={selectedStratagemIds}
              onChange={setSelectedStratagemIds}
            />
            <StratagemPicker
              side="Defender"
              stratagems={defenderStratagems}
              selectedIds={selectedDefenderStratagemIds}
              onChange={setSelectedDefenderStratagemIds}
            />
          </fieldset>
        )}
        {(attackerRuleAbilities.length > 0 || defenderRuleAbilities.length > 0) && (
          <fieldset className="form-section">
            <legend>Faction Rules</legend>
            <RuleOptionPicker
              side="Attacker"
              abilities={attackerRuleAbilities}
              choices={effectiveChoices(attackerRuleAbilities, attackerRuleChoices)}
              onChange={setAttackerRuleChoices}
            />
            <RuleOptionPicker
              side="Defender"
              abilities={defenderRuleAbilities}
              choices={effectiveChoices(defenderRuleAbilities, defenderRuleChoices)}
              onChange={setDefenderRuleChoices}
            />
          </fieldset>
        )}
        {(!inEngagementRange ||
          attackerPositions.length > 0 ||
          defenderPositions.length > 0) && (
          <fieldset className="form-section">
            <legend>Positioning</legend>
            {!inEngagementRange && (
              <>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={inCover}
                    onChange={(e) => setInCover(e.target.checked)}
                  />
                  Defender in cover (-1 to hit for ranged attacks)
                </label>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={halfRange}
                    onChange={(e) => setHalfRange(e.target.checked)}
                  />
                  Shooting model is within half range
                </label>
              </>
            )}
            <div className="side-columns">
              <PositionPicker
                side="Attacker"
                positions={attackerPositions}
                selectedIds={attackerPositionIds}
                onChange={setAttackerPositionIds}
              />
              <PositionPicker
                side="Defender"
                positions={defenderPositions}
                selectedIds={defenderPositionIds}
                onChange={setDefenderPositionIds}
              />
            </div>
          </fieldset>
        )}
        <fieldset className="form-section">
          <legend>Modifiers</legend>
          {!inEngagementRange && (
            <>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={advanced}
                  onChange={(e) => setAdvanced(e.target.checked)}
                />
                Attacking unit advanced this turn
              </label>
            </>
          )}
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={movedLessThan3}
              onChange={(e) => setMovedLessThan3(e.target.checked)}
            />
            Attacking unit moved less than 3" this turn
          </label>
          {inEngagementRange && (
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={charged}
                onChange={(e) => setCharged(e.target.checked)}
              />
              Attacking unit charged this turn
            </label>
          )}
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={defenderBattleShocked}
              onChange={(e) => setDefenderBattleShocked(e.target.checked)}
            />
            Defending unit is Battle-shocked
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={attackerDamaged}
              onChange={(e) => setAttackerDamaged(e.target.checked)}
            />
            Attacking model is Damaged (on its Damaged profile)
          </label>
          {hasPrecision && (
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={applyPrecision}
                onChange={(e) => setApplyPrecision(e.target.checked)}
              />
              Apply Precision (precision weapons target leaders, then supports, then other models)
            </label>
          )}
        </fieldset>
        <button type="submit">Calculate</button>
      </form>

      {result && <CombatResults result={result} showFnp={result.defenderHasFnp} />}
    </section>
  )
}

export default CalculatorPanel
