import { useEffect, useState } from 'react'
import { getJudgement, judgeForExecution } from '../api'

// Judged for Execution (Intranzia Fraye - see
// app/seeds/factions/adepta_sororitas/unit_abilities.py): at the end of its
// player's Movement phase (declared during it), it selects an enemy unit
// within 18" of and visible to it - until the start of their next Command
// phase, their ADEPTA SORORITAS units' attacks against it have [LETHAL HITS].
// Shown while a unit can use it, or an enemy unit is judged.

function JudgedPanel({ game, onChange, onError }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getJudgement(game.id)
      .then((s) => !cancelled && setState(s))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  if (!state) return null
  const usable = state.units.filter((u) => !u.reason || u.targets.length > 0)
  if (usable.length === 0 && state.judged.length === 0) return null

  const judge = async (unit, target) => {
    setBusy(true)
    onError(null)
    try {
      setState(
        await judgeForExecution(game.id, { unit_id: unit.unit_id, target_unit_id: target.unit_id })
      )
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="deployment-panel">
      <h3>Judged for Execution</h3>
      {state.judged.length > 0 && (
        <p>
          Judged: {state.judged.map((u) => u.name).join(', ')}{' '}
          <span className="hint">(ADEPTA SORORITAS attacks against them have [LETHAL HITS])</span>
        </p>
      )}
      {usable.map((unit) => (
        <div key={unit.unit_id}>
          <p className="hint">
            {unit.name}, at the end of the Movement phase: select an enemy unit within 18" of and
            visible to it.
          </p>
          <div className="inline-controls">
            {unit.targets.map((t) => (
              <button key={t.unit_id} type="button" disabled={busy} onClick={() => judge(unit, t)}>
                Judge {t.name}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default JudgedPanel
