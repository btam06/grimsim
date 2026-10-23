import { useEffect, useState } from 'react'
import { getChargeTargets } from '../api'

// Charging in the charge phase (see app/services/in_game/charging.py, which
// decides what a unit can reach and whether a charge is allowed). The player
// picks a unit, rolls its charge (2D6, kept for the phase), picks a target
// in reach, drags its models into Engagement Range - every one it can, the
// rest closer - and charges.

function unitStatus(unit) {
  if (unit.charged) return `Charged ${unit.target_name} (rolled ${unit.roll})`
  if (unit.failed) return `Charge failed: rolled ${unit.roll}, nothing in reach`
  if (unit.roll !== null) return `Rolled ${unit.roll} (${unit.dice.join(' + ')})`
  return 'Not charged'
}

function ChargePanel({
  game,
  player,
  charge,
  draft,
  checking,
  onSelectUnit,
  onRoll,
  onTarget,
  onReset,
  onCharge,
  onError,
}) {
  const [targets, setTargets] = useState([])
  const selected = charge?.units.find((u) => u.unit_id === draft.unitId) ?? null
  const rolled = selected?.roll ?? null
  const canMove = selected && rolled !== null && !selected.charged && !selected.failed
  const target = targets.find((t) => t.unit_id === draft.targetId) ?? null
  const check = draft.check

  // The selected unit's possible targets, once it's rolled.
  useEffect(() => {
    setTargets([])
    if (!selected || rolled === null) return
    let cancelled = false
    getChargeTargets(game.id, selected.unit_id)
      .then((t) => !cancelled && setTargets(t))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, selected?.unit_id, rolled])

  if (!charge) return null
  return (
    <div className="deployment-panel">
      <h3>Charge</h3>
      <p>
        <strong>{player?.user_name}</strong> charges.{' '}
        <span className="hint">Any unit can charge, once a phase.</span>
      </p>
      <div className="radio-group">
        {charge.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="charge-unit"
              checked={draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit)}
            />
            {unit.name}
            <span className="hint"> · {unitStatus(unit)}</span>
          </label>
        ))}
      </div>
      {charge.units.length === 0 && <p className="hint">They have no units on the battlefield.</p>}

      {selected && rolled === null && (
        <div className="inline-controls">
          <button type="button" onClick={() => onRoll(selected)}>
            Roll charge (2D6)
          </button>
        </div>
      )}

      {canMove && (
        <>
          <h4>Target</h4>
          <div className="radio-group">
            {targets.map((t) => (
              <label key={t.unit_id} className="radio-option">
                <input
                  type="radio"
                  name="charge-target"
                  disabled={!t.in_reach}
                  checked={draft.targetId === t.unit_id}
                  onChange={() => onTarget(t.unit_id)}
                />
                {t.name}
                <span className="hint">
                  {' '}
                  · {t.distance.toFixed(1)}" away{t.in_reach ? '' : ' · out of reach'}
                </span>
              </label>
            ))}
          </div>
        </>
      )}

      {/* A fixed height, so the board below doesn't jump. */}
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to charge with.</p>}
        {canMove && !target && <p className="hint">Choose a target in reach.</p>}
        {canMove && target && (
          <p className="hint">
            Drag its models - each up to {rolled}" - into Engagement Range (2") of {target.name}:
            every one that can, and the rest closer.
          </p>
        )}
        {canMove && target && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {canMove && target && check?.valid && <p className="deployment-ready">Ready to charge.</p>}
      </div>
      <div className="inline-controls">
        <button
          type="button"
          disabled={!canMove || !target || !check?.valid || checking}
          onClick={onCharge}
        >
          {target ? `Charge ${target.name}` : 'Charge'}
        </button>
        <button type="button" disabled={!canMove} onClick={onReset}>
          Reset
        </button>
      </div>
    </div>
  )
}

export default ChargePanel
