import { useEffect, useState } from 'react'
import { getChargeTargets } from '../api'

// Charging in the charge phase (see app/services/in_game/charging.py, which
// decides what a unit can reach and whether a charge is allowed). The player
// picks a unit, rolls its charge (2D6, kept for the phase), ticks one or more
// targets in reach (within 12"), drags its models so the unit ends engaged
// with every target and no other enemy unit - each model not engaged ending
// closer to a target - and charges. A FLYING unit can take to the skies.

function unitStatus(unit) {
  if (unit.charged) {
    const names = unit.target_names?.length ? unit.target_names.join(', ') : unit.target_name
    return `Charged ${names} (rolled ${unit.roll})`
  }
  if (unit.failed) return `Charge failed: rolled ${unit.roll}, nothing in reach`
  if (unit.roll !== null) {
    const parts = unit.bonus ? [...unit.dice, unit.bonus] : unit.dice
    return `Rolled ${unit.roll} (${parts.join(' + ')})`
  }
  if (unit.reason) return `Can't charge: ${unit.reason}`
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
  onOptions,
  onReset,
  onCharge,
  onError,
}) {
  const [targets, setTargets] = useState([])
  const selected = charge?.units.find((u) => u.unit_id === draft.unitId) ?? null
  const rolled = selected?.roll ?? null
  const canMove = selected && rolled !== null && !selected.charged && !selected.failed
  const targetIds = draft.options?.target_unit_ids ?? (draft.targetId ? [draft.targetId] : [])
  const chosen = targets.filter((t) => targetIds.includes(t.unit_id))
  const target = chosen[0] ?? null
  const names = chosen.map((t) => t.name).join(', ')
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
        <span className="hint">
          Any unit can charge once a phase, unless it Advanced or Fell Back.
        </span>
      </p>
      <div className="radio-group">
        {charge.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="charge-unit"
              disabled={Boolean(unit.reason) && unit.roll === null}
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
      {selected?.can_reroll && (
        // An ability lets it (e.g. Terminatus Assault): once, before it charges.
        <div className="inline-controls">
          <button type="button" onClick={() => onRoll(selected, true)}>
            Re-roll charge
          </button>
        </div>
      )}

      {canMove && (
        <>
          <h4>Targets</h4>
          <div className="radio-group">
            {targets.map((t) => (
              <label key={t.unit_id} className="radio-option">
                <input
                  type="checkbox"
                  disabled={!t.in_reach}
                  checked={targetIds.includes(t.unit_id)}
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
          {selected.can_fly && (
            <label className="radio-option">
              <input
                type="checkbox"
                checked={Boolean(draft.options?.take_to_skies)}
                onChange={(e) => onOptions({ take_to_skies: e.target.checked })}
              />
              Take to the skies
              <span className="hint"> (2" less, through models and terrain)</span>
            </label>
          )}
        </>
      )}

      {/* A fixed height, so the board below doesn't jump. */}
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to charge with.</p>}
        {canMove && !target && <p className="hint">Choose a target in reach.</p>}
        {canMove && target && (
          <p className="hint">
            Drag its models - each up to {rolled}" - so the unit ends engaged (2") with {names}{' '}
            and no other enemy unit; each model that isn't engaged ends closer to a target.
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
          {target ? `Charge ${names}` : 'Charge'}
        </button>
        <button type="button" disabled={!canMove} onClick={onReset}>
          Reset
        </button>
      </div>
    </div>
  )
}

export default ChargePanel
