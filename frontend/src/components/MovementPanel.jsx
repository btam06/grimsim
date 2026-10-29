// Moving units in the movement phase (see app/services/in_game/movement.py, which
// decides what each unit can do and whether a move is allowed). The player
// picks a unit, ticks Advance if it's advancing (its D6 is rolled then, and
// from then on it Advances this phase - no going back to a Normal move, even
// after a reset) - or, within Engagement Range, it Falls Back - and drags any of
// its models: each valid move is saved as it's made, and can be changed (or
// reset) until the phase ends. Units left alone remain stationary. A FLYING
// unit can take to the skies (2" less - none with Hover - but through models
// and terrain); a Super-heavy Walker can be MOBILE for its move (through
// terrain, then a D6: on a 1 it's Battle-shocked).

// How a unit stands this phase.
function unitStatus(unit) {
  if (unit.arrived) return 'Arrived from Reserves'
  if (unit.moved) {
    if (unit.kind === 'advance') return `Advanced (rolled ${unit.advance_roll})`
    if (unit.kind === 'fall_back') return 'Fell back'
    return 'Moved'
  }
  if (unit.in_engagement_range) return 'Within Engagement Range'
  if (unit.advance_roll) return `Rolled ${unit.advance_roll} to Advance`
  return 'Not moved'
}

function MovementPanel({
  player,
  movement,
  draft,
  checking,
  onSelectUnit,
  onToggleAdvance,
  onOptions,
  onReset,
}) {
  if (!movement) return null
  const selected = movement.units.find((u) => u.unit_id === draft.unitId) ?? null
  // Any unit can be moved - again, until the phase ends.
  const canMove = Boolean(selected)
  const check = draft.check
  const kinds = selected?.allowed_kinds ?? []
  const options = draft.options ?? {}

  return (
    <div className="deployment-panel">
      <h3>Movement</h3>
      <p>
        <strong>{player?.user_name}</strong> moves their units.{' '}
        <span className="hint">Units you don't move remain stationary.</span>
      </p>
      <div className="radio-group">
        {movement.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="move-unit"
              disabled={unit.arrived}
              checked={draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit)}
            />
            {unit.name}
            <span className="hint"> · {unitStatus(unit)}</span>
          </label>
        ))}
      </div>
      {movement.units.length === 0 && <p className="hint">They have no units on the battlefield.</p>}

      {canMove && (
        <div className="move-kinds">
          {kinds.includes('fall_back') ? (
            <span className="hint">
              {selected.name} is within Engagement Range: it can only Fall Back.
            </span>
          ) : (
            <label className="radio-option">
              {/* Once it's rolled, it Advances this phase: no unticking. */}
              <input
                type="checkbox"
                checked={draft.kind === 'advance' || Boolean(selected.advance_roll)}
                disabled={Boolean(selected.advance_roll)}
                onChange={(e) => onToggleAdvance(selected, e.target.checked)}
              />
              Advance
              <span className="hint">
                {selected.advance_roll
                  ? ` (rolled ${selected.advance_roll}: M + ${selected.advance_roll}" - now Advancing)`
                  : ' (rolls a D6)'}
              </span>
            </label>
          )}
          {selected.can_fly && (
            <label className="radio-option">
              <input
                type="checkbox"
                checked={Boolean(options.take_to_skies)}
                onChange={(e) => onOptions({ take_to_skies: e.target.checked })}
              />
              Take to the skies
              <span className="hint"> (2" less, through models and terrain)</span>
            </label>
          )}
          {selected.super_heavy_walker && (
            <label className="radio-option">
              <input
                type="checkbox"
                checked={Boolean(options.mobile)}
                onChange={(e) => onOptions({ mobile: e.target.checked })}
              />
              MOBILE
              <span className="hint"> (through terrain; then a D6 - on a 1, Battle-shocked)</span>
            </label>
          )}
        </div>
      )}

      {/* A fixed height, so the board below doesn't jump. */}
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to move.</p>}
        {canMove && (
          <p className="hint">
            Drag any of its models - each up to the dashed ring around where it started the
            phase - keeping them within 9" of every other model in the unit and within 2" of at
            least one. Moves are saved as you make them; you can change them until the phase
            ends.
          </p>
        )}
        {canMove && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {canMove && check?.valid && selected.moved && (
          <p className="deployment-ready">Moved.</p>
        )}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!canMove} onClick={onReset}>
          Reset
        </button>
      </div>
    </div>
  )
}

export default MovementPanel
