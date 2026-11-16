import { useEffect, useState } from 'react'
import { chooseRelics, getRelics } from '../api'

// Relics of the Matriarchs (the Triumph of Saint Katherine - see
// app/seeds/factions/adepta_sororitas/unit_abilities.py): at the start of
// each battle round, up to two of its six auras (one while it's Damaged),
// for friendly ADEPTA SORORITAS units within 6" until the next. Shown while
// it's on the battlefield.

function RelicsPanel({ game, onChange, onError }) {
  const [units, setUnits] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getRelics(game.id)
      .then((u) => !cancelled && setUnits(u))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game])

  if (!units || units.length === 0) return null

  const toggle = async (unit, option) => {
    const chosen = unit.chosen.includes(option)
      ? unit.chosen.filter((o) => o !== option)
      : [...unit.chosen, option].slice(-unit.allowed)
    setBusy(true)
    onError(null)
    try {
      setUnits(await chooseRelics(game.id, { unit_id: unit.unit_id, options: chosen }))
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="deployment-panel">
      <h3>Relics of the Matriarchs</h3>
      {units.map((unit) => (
        <div key={unit.unit_id}>
          <p>
            {unit.name}:{' '}
            {unit.chosen.length ? unit.chosen.join(', ') : 'none this battle round'}{' '}
            <span className="hint">
              {unit.reason ? `(${unit.reason})` : `(select up to ${unit.allowed})`}
            </span>
          </p>
          {!unit.reason && (
            <div className="relic-choices">
              {unit.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={busy}
                  className={`choice-box${unit.chosen.includes(option) ? ' choice-box--chosen' : ''}`}
                  title={unit.descriptions[option]}
                  aria-pressed={unit.chosen.includes(option)}
                  onClick={() => toggle(unit, option)}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default RelicsPanel
