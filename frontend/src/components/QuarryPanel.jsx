import { useEffect, useState } from 'react'
import { getQuarry, selectQuarry } from '../api'

// Quarries (see app/services/in_game/quarry.py): at the start of the battle,
// a unit with an ability like Virtue of Intolerance or Focused Hunters
// selects a unit from the opponent's army as its quarry - its attacks
// against it get the ability's benefit (e.g. re-roll the Hit roll). Some can
// select a new one once it's destroyed (a denuncia oratory). Shown while a
// unit has one or can select one.

function QuarryPanel({ game, onChange, onError }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getQuarry(game.id)
      .then((s) => !cancelled && setState(s))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game])

  if (!state || state.units.length === 0) return null

  const select = async (unit, target) => {
    setBusy(true)
    onError(null)
    try {
      setState(await selectQuarry(game.id, { unit_id: unit.unit_id, target_unit_id: target.unit_id }))
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="deployment-panel">
      <h3>Quarries</h3>
      {state.units.map((unit) => (
        <div key={unit.unit_id}>
          <p>
            {unit.name} ({unit.ability}):{' '}
            {unit.quarry ? `quarry ${unit.quarry.name}` : 'no quarry yet'}{' '}
            {unit.hint && <span className="hint">({unit.hint})</span>}
          </p>
          {unit.targets.length > 0 && (
            <div className="inline-controls">
              {unit.targets.map((t) => (
                <button
                  key={t.unit_id}
                  type="button"
                  disabled={busy}
                  onClick={() => select(unit, t)}
                >
                  Quarry: {t.name}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default QuarryPanel
