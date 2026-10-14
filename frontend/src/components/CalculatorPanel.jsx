import { useEffect, useMemo, useState } from 'react'
import {
  listEffects,
  listFactionAbilities,
  listFactionUnits,
  listLists,
  listModels,
  listStratagems,
  listUnits,
  listWeaponAbilities,
  listWeapons,
  runCombat,
} from '../api'
import Field from './Field'
import Select from './Select'

const DIE_FACES = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅']
const diceFace = (roll) => DIE_FACES[roll - 1] ?? roll

function DiceRolls({ rolls }) {
  if (rolls.length === 0) return 'none'
  return rolls.map((roll, i) => (
    <span key={i} className="die-face">
      {diceFace(roll)}
    </span>
  ))
}

// One radio group per faction ability with rule options (e.g. Doctrina
// Imperatives), for picking which option is active for one side - or none.
function RuleOptionPicker({ side, abilities, choices, onChange }) {
  return abilities.map((ability) => (
    <div key={ability.id} className="radio-group">
      {side} — {ability.name}
      {['', ...ability.rule_options].map((option) => (
        <label key={option || 'none'} className="radio-option">
          <input
            type="radio"
            name={`${side}-rule-${ability.id}`}
            checked={(choices[ability.id] ?? '') === option}
            onChange={() => onChange({ ...choices, [ability.id]: option })}
          />
          {option || 'None'}
        </label>
      ))}
    </div>
  ))
}

function CalculatorPanel() {
  const [units, setUnits] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [weapons, setWeapons] = useState([])
  const [lists, setLists] = useState([])
  const [stratagems, setStratagems] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [effects, setEffects] = useState([])
  const [models, setModels] = useState([])
  const [factionAbilities, setFactionAbilities] = useState([])
  // {faction ability id: selected rule option name ('' for none)}, per side.
  const [attackerRuleChoices, setAttackerRuleChoices] = useState({})
  const [defenderRuleChoices, setDefenderRuleChoices] = useState({})
  const [attackingUnitId, setAttackingUnitId] = useState('')
  const [defendingUnitId, setDefendingUnitId] = useState('')
  const [inEngagementRange, setInEngagementRange] = useState(false)
  const [inCover, setInCover] = useState(false)
  const [halfRange, setHalfRange] = useState(false)
  const [movedLessThan3, setMovedLessThan3] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [selectedWeaponNames, setSelectedWeaponNames] = useState([])
  const [selectedStratagemIds, setSelectedStratagemIds] = useState([])
  const [applyPrecision, setApplyPrecision] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listUnits().then(setUnits).catch((err) => setError(err.message))
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
    listLists().then(setLists).catch((err) => setError(err.message))
    listStratagems().then(setStratagems).catch((err) => setError(err.message))
    listWeaponAbilities().then(setWeaponAbilities).catch((err) => setError(err.message))
    listEffects().then(setEffects).catch((err) => setError(err.message))
    listModels().then(setModels).catch((err) => setError(err.message))
    listFactionAbilities().then(setFactionAbilities).catch((err) => setError(err.message))
  }, [])

  const unitLabel = (unit) => {
    const name = factionUnits.find((fu) => fu.id === unit.faction_unit_id)?.name ?? `#${unit.faction_unit_id}`
    return `${name} (unit #${unit.id})`
  }

  const unitOptions = units.map((u) => ({ id: u.id, name: unitLabel(u) }))

  const attackingUnit = units.find((u) => u.id === Number(attackingUnitId))

  // Weapons sharing a name (e.g. one per model in a 5-model squad) are
  // grouped into a single checklist entry - checking it selects every
  // underlying weapon id in the group.
  const weaponGroups = useMemo(() => {
    if (!attackingUnit) return []
    const weaponIds = attackingUnit.unit_models.flatMap((um) => um.weapon_ids)
    const groups = new Map()
    weaponIds.forEach((id) => {
      const weapon = weapons.find((w) => w.id === id)
      if (!weapon) return
      if (!groups.has(weapon.name)) groups.set(weapon.name, [])
      groups.get(weapon.name).push(id)
    })
    return Array.from(groups.entries()).map(([name, ids]) => ({ name, weaponIds: ids }))
  }, [attackingUnit, weapons])

  // Default every weapon group to selected whenever the attacking unit
  // changes (or its weapons finish loading).
  useEffect(() => {
    setSelectedWeaponNames(weaponGroups.map((g) => g.name))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attackingUnitId, weapons])

  // Core stratagems are always available; detachment stratagems only when
  // the attacking unit's army list has taken one of their detachments.
  const availableStratagems = useMemo(() => {
    const list = lists.find((l) => l.id === attackingUnit?.list_id)
    const detachmentIds = list?.detachment_ids ?? []
    return stratagems.filter(
      (s) => s.is_core || s.detachment_ids.some((id) => detachmentIds.includes(id))
    )
  }, [attackingUnit, lists, stratagems])

  // Stratagems are opt-in, so clear them whenever the attacking unit changes.
  useEffect(() => {
    setSelectedStratagemIds([])
  }, [attackingUnitId])

  // Faction abilities with rule options held by any model in a unit - a unit
  // gains an option if one of its models has the ability.
  const ruleAbilitiesFor = (unit) => {
    if (!unit) return []
    const heldIds = new Set(
      unit.unit_models.flatMap(
        (um) => models.find((m) => m.id === um.model_id)?.faction_ability_ids ?? []
      )
    )
    return factionAbilities.filter((a) => heldIds.has(a.id) && a.rule_options.length > 0)
  }
  const defendingUnit = units.find((u) => u.id === Number(defendingUnitId))
  const attackerRuleAbilities = ruleAbilitiesFor(attackingUnit)
  const defenderRuleAbilities = ruleAbilitiesFor(defendingUnit)

  useEffect(() => {
    setAttackerRuleChoices({})
  }, [attackingUnitId])

  useEffect(() => {
    setDefenderRuleChoices({})
  }, [defendingUnitId])

  // Only send choices for abilities the unit currently has.
  const selectedRuleOptions = (abilities, choices) =>
    abilities.map((a) => choices[a.id]).filter(Boolean)

  // Precision is only worth offering when something about to attack has the
  // precision effect - a selected weapon's ability, or a selected stratagem.
  const hasPrecision = useMemo(() => {
    const precisionEffectId = effects.find((e) => e.keyword === 'precision')?.id
    if (precisionEffectId === undefined) return false
    const precisionAbilityIds = new Set(
      weaponAbilities.filter((a) => a.effect_ids.includes(precisionEffectId)).map((a) => a.id)
    )
    const weaponHasPrecision = weaponGroups
      .filter((g) => selectedWeaponNames.includes(g.name))
      .flatMap((g) => g.weaponIds)
      .some((id) =>
        weapons.find((w) => w.id === id)?.ability_ids.some((aid) => precisionAbilityIds.has(aid))
      )
    const stratagemHasPrecision = stratagems.some(
      (s) => selectedStratagemIds.includes(s.id) && s.effect_ids.includes(precisionEffectId)
    )
    return weaponHasPrecision || stratagemHasPrecision
  }, [effects, weaponAbilities, weaponGroups, selectedWeaponNames, weapons, stratagems, selectedStratagemIds])

  const toggleStratagemId = (id) => {
    setSelectedStratagemIds((ids) =>
      ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]
    )
  }

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
      const selectedWeaponIds = weaponGroups
        .filter((g) => selectedWeaponNames.includes(g.name))
        .flatMap((g) => g.weaponIds)
      const response = await runCombat({
        attacking_unit_id: Number(attackingUnitId),
        defending_unit_id: Number(defendingUnitId),
        selected_weapon_ids: selectedWeaponIds,
        stratagem_ids: selectedStratagemIds,
        apply_precision: hasPrecision && applyPrecision,
        attacker_rule_options: selectedRuleOptions(attackerRuleAbilities, attackerRuleChoices),
        defender_rule_options: selectedRuleOptions(defenderRuleAbilities, defenderRuleChoices),
        in_engagement_range: inEngagementRange,
        in_cover: inCover,
        half_range: halfRange,
        moved_less_than_3: movedLessThan3,
        advanced,
      })
      setResult(response)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Calculator</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleCalculate}>
        <Field label="Attacking Unit">
          <Select
            options={unitOptions}
            value={attackingUnitId}
            onChange={setAttackingUnitId}
            placeholder="Select attacking unit"
          />
        </Field>
        <Field label="Defending Unit">
          <Select
            options={unitOptions}
            value={defendingUnitId}
            onChange={setDefendingUnitId}
            placeholder="Select defending unit"
          />
        </Field>
        {weaponGroups.length > 0 && (
          <div className="checkbox-group">
            Weapons to Shoot
            <div className="checkbox-grid">
              {weaponGroups.map((g) => (
                <label key={g.name} className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={selectedWeaponNames.includes(g.name)}
                    onChange={() => toggleWeaponName(g.name)}
                  />
                  {g.name}
                </label>
              ))}
            </div>
          </div>
        )}
        {attackingUnit && availableStratagems.length > 0 && (
          <div className="checkbox-group">
            Stratagems
            <div className="checkbox-grid">
              {availableStratagems.map((s) => (
                <label key={s.id} className="checkbox-field" title={s.description ?? ''}>
                  <input
                    type="checkbox"
                    checked={selectedStratagemIds.includes(s.id)}
                    onChange={() => toggleStratagemId(s.id)}
                  />
                  {s.name} ({s.cp} CP{s.is_core ? ', Core' : ''})
                </label>
              ))}
            </div>
          </div>
        )}
        {(attackerRuleAbilities.length > 0 || defenderRuleAbilities.length > 0) && (
          <fieldset className="form-section">
            <legend>Faction Rules</legend>
            <RuleOptionPicker
              side="Attacker"
              abilities={attackerRuleAbilities}
              choices={attackerRuleChoices}
              onChange={setAttackerRuleChoices}
            />
            <RuleOptionPicker
              side="Defender"
              abilities={defenderRuleAbilities}
              choices={defenderRuleChoices}
              onChange={setDefenderRuleChoices}
            />
          </fieldset>
        )}
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
        <fieldset className="form-section">
          <legend>Modifiers</legend>
          {!inEngagementRange && (
            <>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={inCover}
                  onChange={(e) => setInCover(e.target.checked)}
                />
                Defender in cover (+1 to hit for ranged attacks)
              </label>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={halfRange}
                  onChange={(e) => setHalfRange(e.target.checked)}
                />
                Shooting model is within half range
              </label>
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

      {result && (
        <>
          <h3>Results by Weapon</h3>
          {result.weapon_results.length === 0 && <p>No weapons fired.</p>}
          <ul>
            {result.weapon_results.map((wr) => (
              <li key={wr.name}>
                {wr.name}
                <ul>
                  <li>
                    Attack rolls: <DiceRolls rolls={wr.attack_rolls} />
                  </li>
                  <li>
                    Attack rerolls: <DiceRolls rolls={wr.attack_rerolls} />
                  </li>
                  <li>
                    Wound rolls: <DiceRolls rolls={wr.wound_rolls} />
                  </li>
                  <li>
                    Save rolls: <DiceRolls rolls={wr.save_rolls} />
                  </li>
                  <li>Total damage dealt: {wr.total_damage}</li>
                  <li>Defending models destroyed: {wr.models_destroyed}</li>
                  {wr.hazardous_rolls.length > 0 && (
                    <>
                      <li>
                        Hazardous rolls: <DiceRolls rolls={wr.hazardous_rolls} />
                      </li>
                      <li>Hazardous wounds taken: {wr.hazardous_wounds}</li>
                    </>
                  )}
                </ul>
              </li>
            ))}
          </ul>

          <h3>Overall</h3>
          <ul>
            <li>Total damage dealt: {result.total_damage}</li>
            <li>Defending models destroyed: {result.models_destroyed}</li>
            <li>Defending models remaining: {result.defending_models_remaining}</li>
            {result.hazardous_rolls.length > 0 && (
              <>
                <li>Hazardous wounds taken: {result.hazardous_wounds}</li>
                <li>Hazardous attackers destroyed: {result.hazardous_models_destroyed}</li>
              </>
            )}
          </ul>
        </>
      )}
    </section>
  )
}

export default CalculatorPanel
