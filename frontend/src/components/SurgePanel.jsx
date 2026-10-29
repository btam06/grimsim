import { useState } from 'react'
import Select from './Select'

// Surge moves (21.02 - see app/services/in_game/surge.py): when a rule lets
// a unit make one (e.g. a Necron unit that lost models to an enemy's
// shooting), its player says so here - how far ("D6" is rolled) - and the
// unit moves towards its surge target, the closest enemy unit: each model
// that moves ends engaged with it or closer, and engaged with no other enemy
// unit. Then it can't move again this phase.

function SurgePanel({ game, deployment, surges, draft, checking, onStart, onPick, onSave }) {
  const [unitId, setUnitId] = useState('')
  const [distance, setDistance] = useState('D6')
  if (game.status !== 'in_progress' || !deployment) return null
  const name = (seat) => game.players.find((p) => p.seat === seat)?.user_name ?? `Seat ${seat}`
  const onBattlefield = deployment.units.filter((u) => u.models.some((m) => m.position))
  return (
    <details className="deployment-panel" open={surges.length > 0}>
      <summary>
        <h3 className="inline-heading">Surge moves</h3>
      </summary>
      <p className="hint">
        When a rule lets a unit make a surge move: pick it and how far (D6 is rolled).
      </p>
      <div className="command-target">
        <Select
          options={onBattlefield.map((u) => ({
            id: String(u.unit_id),
            name: `${u.name} (${name(u.seat)})`,
          }))}
          value={unitId}
          onChange={setUnitId}
          placeholder="Unit"
        />
        <input
          type="text"
          className="short-input"
          value={distance}
          onChange={(e) => setDistance(e.target.value)}
          title='"D6", or a number of inches'
        />
        <button
          type="button"
          disabled={!unitId}
          onClick={() => onStart({ unit_id: Number(unitId), distance })}
        >
          Surge
        </button>
      </div>
      {surges.length > 0 && (
        <ul className="round-start-rules">
          {surges.map((m) => {
            const picked = draft.kind === 'surge' && draft.unitId === m.unit_id
            return (
              <li key={m.unit_id}>
                <strong>{m.name}</strong>
                <span className="hint">
                  {' '}
                  · {name(m.seat)} · up to {m.distance}" towards {m.target_name}
                </span>
                <div className="inline-controls">
                  <button type="button" onClick={() => onPick(m)}>
                    {picked ? 'Moving…' : 'Move'}
                  </button>
                  {picked && (
                    <button
                      type="button"
                      disabled={checking || !draft.check?.valid}
                      onClick={onSave}
                    >
                      Save move
                    </button>
                  )}
                </div>
                {picked && draft.check && !draft.check.valid && (
                  <p className="error">{draft.check.problems.join('; ')}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </details>
  )
}

export default SurgePanel
