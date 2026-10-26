import { useEffect, useState } from 'react'

// Emergency disembarking (see app/services/in_game/emergency.py, which
// decides where a unit can go): a transport was destroyed with units inside,
// and its owner sets each up within 3" of where it was - touching it if they
// can. Models left out are destroyed; those set up take a hazard roll, and
// once every unit is out the transport's Deadly Demise rolls. The game waits
// until they're all out.

function rollText(roll) {
  if (roll.kind === 'hazard') {
    return `${roll.name}: hazard roll ${roll.roll}${roll.wounds ? `, ${roll.wounds} mortal wounds` : ''}`
  }
  if (roll.kind === 'deadly_demise') {
    return `Deadly Demise: rolled ${roll.roll}${roll.roll === 6 ? ' - it explodes' : ''}`
  }
  return `${roll.name}: ${roll.wounds} mortal wounds from the explosion`
}

function EmergencyPanel({ game, emergency, draft, checking, onSelectUnit, onToggleModel, onPlace }) {
  // How many of the game's rolls have been seen and dismissed - on first
  // load, any from before (with nothing waiting) count as seen.
  const [seen, setSeen] = useState(null)
  useEffect(() => {
    if (seen === null && emergency) {
      setSeen(emergency.units.length === 0 ? emergency.rolls.length : 0)
    }
  }, [emergency, seen])
  if (!emergency || seen === null) return null
  const { units } = emergency
  const rolls = emergency.rolls.slice(seen)
  if (units.length === 0 && rolls.length === 0) return null
  const selected = draft.kind === 'emergency' ? units.find((u) => u.unit_id === draft.unitId) : null
  const check = selected ? draft.check : null

  return (
    <div className="deployment-panel">
      <h3>Emergency disembark</h3>
      {units.length > 0 && (
        <>
          <p className="hint">
            A transport was destroyed with units inside. Set each up within 3" of it, touching it
            if they can - any model left out is destroyed. Each model set up then takes a hazard
            roll.
          </p>
          <div className="radio-group">
            {units.map((unit) => (
              <label key={unit.unit_id} className="radio-option">
                <input
                  type="radio"
                  name="emergency-unit"
                  checked={selected?.unit_id === unit.unit_id}
                  onChange={() => onSelectUnit(unit)}
                />
                {unit.name}
                <span className="hint">
                  {' '}
                  · {game.players.find((p) => p.seat === unit.seat)?.user_name}'s, from{' '}
                  {unit.transport_name}
                </span>
              </label>
            ))}
          </div>
          {selected && (
            <div className="checkbox-grid">
              {selected.models.map((m) => (
                <label key={m.unit_model_id} className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={draft.positions?.[m.unit_model_id] !== undefined}
                    onChange={() => onToggleModel(selected, m.unit_model_id)}
                  />
                  {m.name}
                </label>
              ))}
            </div>
          )}
          <div className="deployment-status">
            {!selected && <p className="hint">Choose a unit to set up.</p>}
            {selected && (
              <p className="hint">Drag the models into place; untick any that can't fit.</p>
            )}
            {check && !check.valid && (
              <ul className="deployment-problems">
                {check.problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            )}
            {check?.valid && <p className="deployment-ready">Ready to set up.</p>}
          </div>
          <div className="inline-controls">
            <button type="button" disabled={!selected || !check?.valid || checking} onClick={onPlace}>
              {selected ? `Set up ${selected.name}` : 'Set up'}
            </button>
          </div>
        </>
      )}
      {rolls.length > 0 && (
        <>
          <ul className="round-start-rules">
            {rolls.map((roll, i) => (
              <li key={i} className="hint">
                {rollText(roll)}
              </li>
            ))}
          </ul>
          {units.length === 0 && (
            <div className="inline-controls">
              <button type="button" onClick={() => setSeen(emergency.rolls.length)}>
                Dismiss
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default EmergencyPanel
