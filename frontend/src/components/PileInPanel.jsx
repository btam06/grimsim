// Piling in at the start of the fight phase (see
// app/services/in_game/fighting.py, which decides who can pile in and whether
// a pile-in is allowed). The player whose turn it is piles in first, then
// their opponent; each picks their units within Engagement Range, drags their
// models - up to 3" each, closer to the nearest enemy; those in base contact
// stay put - and says when they're done.

function unitStatus(unit) {
  if (unit.piled_in) return 'Piled in'
  if (!unit.engaged) return 'Not in Engagement Range'
  if (unit.locked_unit_model_ids.length > 0) {
    return `${unit.locked_unit_model_ids.length} in base contact (can't move)`
  }
  return 'Can pile in'
}

function PileInPanel({
  game,
  pileIn,
  draft,
  checking,
  onSelectUnit,
  onReset,
  onPileIn,
  onDone,
}) {
  if (!pileIn) return null
  if (pileIn.seat === null) {
    return (
      <div className="deployment-panel">
        <h3>Pile in</h3>
        <p className="hint">Both players have piled in.</p>
      </div>
    )
  }
  const player = game.players.find((p) => p.seat === pileIn.seat)
  const selected = pileIn.units.find((u) => u.unit_id === draft.unitId) ?? null
  const canMove = selected?.can_pile_in && draft.positions !== null
  const check = draft.check
  const first = pileIn.seat === game.turn_seat

  return (
    <div className="deployment-panel">
      <h3>Pile in</h3>
      <p>
        <strong>{player?.user_name}</strong> piles in{first ? ' first' : ''}.{' '}
        <span className="hint">
          Units within Engagement Range only; models in base contact stay put.
        </span>
      </p>
      <div className="radio-group">
        {pileIn.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="pile-in-unit"
              disabled={!unit.can_pile_in}
              checked={draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit)}
            />
            {unit.name}
            <span className="hint"> · {unitStatus(unit)}</span>
          </label>
        ))}
      </div>
      {pileIn.units.length === 0 && <p className="hint">They have no units on the battlefield.</p>}

      {/* A fixed height, so the board below doesn't jump. */}
      <div className="deployment-status">
        {!canMove && <p className="hint">Choose a unit to pile in, or finish.</p>}
        {canMove && (
          <p className="hint">
            Drag its models - each up to 3", ending closer to the nearest enemy model - keeping
            the unit in coherency and within Engagement Range.
          </p>
        )}
        {canMove && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {canMove && check?.valid && <p className="deployment-ready">Ready to pile in.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!canMove || !check?.valid || checking} onClick={onPileIn}>
          {selected ? `Pile in ${selected.name}` : 'Pile in'}
        </button>
        <button type="button" disabled={!canMove} onClick={onReset}>
          Reset
        </button>
        <button type="button" onClick={() => onDone(pileIn.seat)}>
          Done piling in
        </button>
      </div>
    </div>
  )
}

export default PileInPanel
