import { useEffect, useState } from 'react'
import { listFactionUnits, listUnits, runCombat } from '../api'
import Field from './Field'

function CalculatorPanel() {
  const [units, setUnits] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [attackingUnitId, setAttackingUnitId] = useState('')
  const [defendingUnitId, setDefendingUnitId] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listUnits().then(setUnits).catch((err) => setError(err.message))
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
  }, [])

  const unitLabel = (unit) => {
    const name = factionUnits.find((fu) => fu.id === unit.faction_unit_id)?.name ?? `#${unit.faction_unit_id}`
    return `${name} (unit #${unit.id})`
  }

  const handleCalculate = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    try {
      const attackingUnit = units.find((u) => u.id === Number(attackingUnitId))
      const selectedWeaponIds = attackingUnit.unit_models.flatMap((um) => um.weapon_ids)
      const response = await runCombat({
        attacking_unit_id: Number(attackingUnitId),
        defending_unit_id: Number(defendingUnitId),
        selected_weapon_ids: selectedWeaponIds,
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
        <button type="submit">Calculate</button>
      </form>

      {result && (
        <ul>
          <li>Total attacks: {result.total_attacks}</li>
          <li>Total hits: {result.total_hits}</li>
          <li>Total wounds: {result.total_wounds}</li>
          <li>Failed saves: {result.failed_saves}</li>
          <li>Total damage dealt: {result.total_damage}</li>
          <li>Defending models destroyed: {result.models_destroyed}</li>
          <li>Defending models remaining: {result.defending_models_remaining}</li>
        </ul>
      )}
    </section>
  )
}

export default CalculatorPanel
