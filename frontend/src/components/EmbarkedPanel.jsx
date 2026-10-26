import { useState } from 'react'
import Select from './Select'

// Disembarking from transports (see app/services/in_game/embarked.py, which
// decides where a unit can disembark). In their movement phase, a player
// picks a unit embarked in one of their transports on the battlefield,
// clicks near the transport to set it down, arranges its models (each wholly
// within 3" of the transport) and disembarks it. If the transport has
// already moved this phase, that's the unit's move. A unit that's made its
// move with every model within 3" of one of their transports can embark in
// it instead (not in the same phase as disembarking).

function EmbarkSection({ embarkable, onEmbark }) {
  // The transport picked for each unit (the first it can reach, until changed).
  const [picked, setPicked] = useState({})
  if (embarkable.length === 0) return null
  return (
    <>
      <h4>Embark</h4>
      <p className="hint">
        These units have moved, ending every model within 3" of a transport.
      </p>
      <ul className="round-start-rules">
        {embarkable.map((unit) => {
          const transportId = picked[unit.unit_id] ?? unit.transports[0].unit_id
          const transport = unit.transports.find((t) => t.unit_id === transportId)
          return (
            <li key={unit.unit_id}>
              <strong>{unit.name}</strong>
              {unit.transports.length > 1 && (
                <div className="command-target">
                  <span className="hint">Transport:</span>
                  <Select
                    options={unit.transports.map((t) => ({ id: String(t.unit_id), name: t.name }))}
                    value={String(transportId)}
                    onChange={(value) =>
                      value && setPicked((p) => ({ ...p, [unit.unit_id]: Number(value) }))
                    }
                  />
                </div>
              )}
              <div className="inline-controls">
                <button type="button" onClick={() => onEmbark(unit.unit_id, transportId)}>
                  Embark in {transport?.name}
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}

function EmbarkedPanel({
  game,
  embarked,
  draft,
  checking,
  onSelectUnit,
  onPickUp,
  onDisembark,
  onEmbark,
}) {
  if (!embarked || embarked.seat === null) return null
  const embarkable = embarked.embarkable ?? []
  if (embarked.units.length === 0 && embarkable.length === 0) return null
  if (embarked.units.length === 0) {
    return (
      <div className="deployment-panel">
        <h3>Transports</h3>
        <EmbarkSection embarkable={embarkable} onEmbark={onEmbark} />
      </div>
    )
  }
  const player = game.players.find((p) => p.seat === embarked.seat)
  const selected = embarked.units.find((u) => u.unit_id === draft.unitId) ?? null
  const placed = selected && draft.kind === 'disembark' && draft.positions !== null
  const check = draft.kind === 'disembark' ? draft.check : null

  return (
    <div className="deployment-panel">
      <h3>Embarked units</h3>
      <p>
        <strong>{player?.user_name}</strong> can disembark units from their transports.{' '}
        <span className="hint">
          Every model wholly within 3" of its transport, not within Engagement Range of an
          enemy. If the transport has already moved this phase, that's the unit's move.
        </span>
      </p>
      <div className="radio-group">
        {embarked.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="embarked-unit"
              checked={draft.kind === 'disembark' && draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit.unit_id)}
            />
            {unit.name}
            <span className="hint"> · in {unit.transport_name}</span>
          </label>
        ))}
      </div>
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to disembark.</p>}
        {selected && !placed && (
          <p className="hint">Click the board next to its transport, {selected.transport_name}.</p>
        )}
        {placed && <p className="hint">Drag the models into place.</p>}
        {placed && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {placed && check?.valid && <p className="deployment-ready">Ready to disembark.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!placed || !check?.valid || checking} onClick={onDisembark}>
          {selected ? `Disembark ${selected.name}` : 'Disembark'}
        </button>
        <button type="button" disabled={!placed} onClick={onPickUp}>
          Pick up
        </button>
      </div>
      <EmbarkSection embarkable={embarkable} onEmbark={onEmbark} />
    </div>
  )
}

export default EmbarkedPanel
