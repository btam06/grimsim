import { useEffect, useState } from 'react'
import { getHagiomnifex, selectHagiomnifexAbility } from '../api'

// Hagiomnifex (the Sanctified Orators upgrade - see
// app/seeds/factions/adepta_sororitas/hagiomnifex.py): once per turn, at the
// start of a phase (before anything's happened in it), a unit with it selects
// one of its abilities, in play for the rest of the phase. Shown while a unit
// can select one, or has one in play.

const DESCRIPTIONS = {
  'Rite of Revelation': 'while this unit is shooting, enemy units have +6" detection range',
  'Sermon of Intolerance': "this unit's Battle-shock rolls automatically succeed",
  'Catechism of Raging Fervour': 'this unit has +1" M',
  'Psalm of Righteous Smiting': "this unit's attacks have +1 S",
  'Chorus of Repudiation': "attacks that target this unit with S greater than its T have -1 to wound",
}

function HagiomnifexPanel({ game, onChange, onError }) {
  const [units, setUnits] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getHagiomnifex(game.id)
      .then((u) => !cancelled && setUnits(u))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  const shown = units.filter((u) => u.active || !u.reason)
  if (shown.length === 0) return null
  const nameOf = (seat) => game.players.find((p) => p.seat === seat)?.user_name

  const select = async (unit, ability) => {
    setBusy(true)
    onError(null)
    try {
      setUnits(await selectHagiomnifexAbility(game.id, { unit_id: unit.unit_id, ability }))
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="deployment-panel">
      <h3>Hagiomnifex</h3>
      {shown.map((unit) => (
        <div key={unit.unit_id}>
          <p>
            <strong>{unit.name}</strong> <span className="hint">({nameOf(unit.seat)})</span>
            {unit.active && (
              <>
                {' '}
                · {unit.active}: <span className="hint">{DESCRIPTIONS[unit.active]}</span>
              </>
            )}
          </p>
          {!unit.reason && (
            <>
              <p className="hint">At the start of the phase, once a turn: select one.</p>
              <div className="inline-controls">
                {unit.abilities.map((ability) => (
                  <button
                    key={ability}
                    type="button"
                    disabled={busy}
                    title={DESCRIPTIONS[ability]}
                    onClick={() => select(unit, ability)}
                  >
                    {ability}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

export default HagiomnifexPanel
