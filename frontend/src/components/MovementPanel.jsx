// Moving units in the movement phase (see app/services/in_game/movement.py, which
// decides what each unit can do and whether a move is allowed). The player
// picks a unit, ticks Advance if it's advancing (its D6 is rolled the first
// time, and kept: unticking makes it a Normal move, ticking again uses the
// same roll) - or, within Engagement Range, it Falls Back - drags any of its
// models, and moves it. Units left alone remain stationary.

// How a unit stands this phase.
function unitStatus(unit) {
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
  onReset,
  onMove,
}) {
  if (!movement) return null
  const selected = movement.units.find((u) => u.unit_id === draft.unitId) ?? null
  const canMove = selected && !selected.moved
  const check = draft.check
  const kinds = selected?.allowed_kinds ?? []

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
              <input
                type="checkbox"
                checked={draft.kind === 'advance'}
                onChange={(e) => onToggleAdvance(selected, e.target.checked)}
              />
              Advance
              <span className="hint">
                {selected.advance_roll
                  ? ` (rolled ${selected.advance_roll}: M + ${selected.advance_roll}")`
                  : ' (rolls a D6)'}
              </span>
            </label>
          )}
        </div>
      )}

      {/* A fixed height, so the board below doesn't jump. */}
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to move.</p>}
        {selected?.moved && <p className="hint">{selected.name} has already moved this phase.</p>}
        {canMove && (
          <p className="hint">
            Drag any of its models - each up to the dashed ring around where it started -
            keeping them within 9" of every other model in the unit and within 2" of at least one.
          </p>
        )}
        {canMove && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {canMove && check?.valid && <p className="deployment-ready">Ready to move.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!canMove || !check?.valid || checking} onClick={onMove}>
          {selected ? `Move ${selected.name}` : 'Move'}
        </button>
        <button type="button" disabled={!canMove} onClick={onReset}>
          Reset
        </button>
      </div>
    </div>
  )
}

export default MovementPanel
