import { useEffect, useState } from 'react'
import { useBoardOverlay } from '../boardOverlay'
import { getShootingStart, applyShootingStart } from '../api'
import Select from './Select'

// The start of the Shooting phase (see app/services/in_game/shooting_start.py):
// abilities used before any of the player's units shoot - e.g. Secutor of
// Olympus: pick an enemy VEHICLE unit within 12" and roll for mortal wounds.

function ShootingStartPanel({ game, refreshKey, onUsed, onError }) {
  const [abilities, setAbilities] = useState([])
  const [targets, setTargets] = useState({})
  const [results, setResults] = useState([])
  // The units picked, highlighted on the board.
  useBoardOverlay('shooting-start', {
    unitIds: Object.values(targets).filter(Boolean).map(Number),
  })

  useEffect(() => {
    let cancelled = false
    getShootingStart(game.id)
      .then((a) => !cancelled && setAbilities(a))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, refreshKey])

  const key = (a) => `${a.unit_id}-${a.ability}`
  const use = async (a) => {
    try {
      const result = await applyShootingStart(game.id, {
        unit_id: a.unit_id,
        ability: a.ability,
        target_unit_id: Number(targets[key(a)]),
      })
      const target = a.targets.find((t) => String(t.unit_id) === String(targets[key(a)]))
      setResults((r) => [...r, { ...result, ability: a.ability, target: target?.name }])
      onUsed()
    } catch (err) {
      onError(err.message)
    }
  }

  if (abilities.length === 0 && results.length === 0) return null
  return (
    <div className="deployment-panel">
      <h3>Start of the Shooting phase</h3>
      {abilities.map((a) => (
        <div key={key(a)}>
          <p>
            <strong>{a.unit_name}</strong>: {a.ability}
          </p>
          {a.description && <p className="hint">{a.description}</p>}
          <div className="inline-controls">
            <Select
              options={a.targets.map((t) => ({ id: t.unit_id, name: t.name }))}
              value={targets[key(a)] ?? ''}
              onChange={(id) => setTargets({ ...targets, [key(a)]: id })}
              placeholder={a.targets.length ? 'Select target' : 'No unit in range'}
            />
            <button type="button" disabled={!targets[key(a)]} onClick={() => use(a)}>
              Use
            </button>
          </div>
        </div>
      ))}
      {results.map((r, i) => (
        <p key={i} className="hint">
          {r.ability} on {r.target}: rolled {r.roll}
          {r.wounds ? ` — ${r.wounds} mortal wounds` : ' — no effect'}
        </p>
      ))}
    </div>
  )
}

export default ShootingStartPanel
