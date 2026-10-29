import { useEffect, useState } from 'react'
import { useBoardOverlay } from '../boardOverlay'
import { listRallies, listRepairs, rallyUnit, repairModel } from '../api'
import Select from './Select'

// Abilities used on one friendly unit or model when the player chooses (see
// app/services/in_game/rally.py and repair.py): rallying a Battle-shocked
// unit (e.g. Servo-skull Uplink, once per battle), and repairing a model in
// the Command phase (e.g. Omnissiah's Blessing).

function AbilityActionsPanel({ game, onAction, onError }) {
  const [rallies, setRallies] = useState([])
  const [repairs, setRepairs] = useState([])
  const [picked, setPicked] = useState({})
  // The units picked to rally, highlighted on the board.
  useBoardOverlay('ability-actions', {
    unitIds: Object.entries(picked)
      .filter(([k, id]) => k.startsWith('rally') && id)
      .map(([, id]) => Number(id)),
  })

  useEffect(() => {
    let cancelled = false
    Promise.all([listRallies(game.id), listRepairs(game.id)])
      .then(([r, p]) => {
        if (cancelled) return
        setRallies(r.filter((a) => a.targets.length > 0))
        setRepairs(p.filter((a) => a.targets.length > 0))
      })
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  if (rallies.length === 0 && repairs.length === 0) return null
  const key = (kind, a) => `${kind}-${a.unit_id}-${a.ability}`
  return (
    <div className="deployment-panel">
      <h3>Abilities</h3>
      {rallies.map((a) => (
        <div key={key('rally', a)} className="inline-controls">
          <span>
            <strong>{a.unit_name}</strong>: {a.ability}
          </span>
          <Select
            options={a.targets.map((t) => ({ id: t.unit_id, name: t.name }))}
            value={picked[key('rally', a)] ?? ''}
            onChange={(id) => setPicked({ ...picked, [key('rally', a)]: id })}
            placeholder="Battle-shocked unit"
          />
          <button
            type="button"
            disabled={!picked[key('rally', a)]}
            onClick={() =>
              onAction(() =>
                rallyUnit(game.id, {
                  unit_id: a.unit_id,
                  ability: a.ability,
                  target_unit_id: Number(picked[key('rally', a)]),
                })
              )
            }
          >
            Use
          </button>
        </div>
      ))}
      {repairs.map((a) => (
        <div key={key('repair', a)} className="inline-controls">
          <span>
            <strong>{a.unit_name}</strong>: {a.ability}
          </span>
          <Select
            options={a.targets.map((t) => ({
              id: t.unit_model_id,
              name: `${t.name} (${t.unit_name})`,
            }))}
            value={picked[key('repair', a)] ?? ''}
            onChange={(id) => setPicked({ ...picked, [key('repair', a)]: id })}
            placeholder="Model"
          />
          <button
            type="button"
            disabled={!picked[key('repair', a)]}
            onClick={() =>
              onAction(() =>
                repairModel(game.id, {
                  unit_id: a.unit_id,
                  ability: a.ability,
                  unit_model_id: Number(picked[key('repair', a)]),
                })
              )
            }
          >
            Use
          </button>
        </div>
      ))}
    </div>
  )
}

export default AbilityActionsPanel
