import { useEffect, useMemo, useState } from 'react'
import { listFactionUnits, listUnits, listWeapons, runCombat } from '../api'
import Field from './Field'

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

function CalculatorPanel() {
  const [units, setUnits] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [weapons, setWeapons] = useState([])
  const [attackingUnitId, setAttackingUnitId] = useState('')
  const [defendingUnitId, setDefendingUnitId] = useState('')
  const [inEngagementRange, setInEngagementRange] = useState(false)
  const [inCover, setInCover] = useState(false)
  const [halfRange, setHalfRange] = useState(false)
  const [movedLessThan3, setMovedLessThan3] = useState(false)
  const [selectedWeaponNames, setSelectedWeaponNames] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listUnits().then(setUnits).catch((err) => setError(err.message))
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
  }, [])

  const unitLabel = (unit) => {
    const name = factionUnits.find((fu) => fu.id === unit.faction_unit_id)?.name ?? `#${unit.faction_unit_id}`
    return `${name} (unit #${unit.id})`
  }

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

  const toggleWeaponName = (name) => {
    setSelectedWeaponNames((names) =>
      names.includes(name) ? names.filter((n) => n !== name) : [...names, name]
    )
  }

  const handleCalculate = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    try {
      const selectedWeaponIds = weaponGroups
        .filter((g) => selectedWeaponNames.includes(g.name))
        .flatMap((g) => g.weaponIds)
      const response = await runCombat({
        attacking_unit_id: Number(attackingUnitId),
        defending_unit_id: Number(defendingUnitId),
        selected_weapon_ids: selectedWeaponIds,
        in_engagement_range: inEngagementRange,
        in_cover: inCover,
        half_range: halfRange,
        moved_less_than_3: movedLessThan3,
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
          <select
            value={attackingUnitId}
            onChange={(e) => setAttackingUnitId(e.target.value)}
            required
          >
            <option value="" disabled>
              Select attacking unit
            </option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {unitLabel(u)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Defending Unit">
          <select
            value={defendingUnitId}
            onChange={(e) => setDefendingUnitId(e.target.value)}
            required
          >
            <option value="" disabled>
              Select defending unit
            </option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {unitLabel(u)}
              </option>
            ))}
          </select>
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
        <div className="radio-group">
          Engagement
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
                  <li>
                    Hazardous rolls: <DiceRolls rolls={wr.hazardous_rolls} />
                  </li>
                  <li>Hazardous wounds taken: {wr.hazardous_wounds}</li>
                </ul>
              </li>
            ))}
          </ul>

          <h3>Overall</h3>
          <ul>
            <li>Total damage dealt: {result.total_damage}</li>
            <li>Defending models destroyed: {result.models_destroyed}</li>
            <li>Defending models remaining: {result.defending_models_remaining}</li>
            <li>Hazardous wounds taken: {result.hazardous_wounds}</li>
            <li>Hazardous attackers destroyed: {result.hazardous_models_destroyed}</li>
          </ul>
        </>
      )}
    </section>
  )
}

export default CalculatorPanel
