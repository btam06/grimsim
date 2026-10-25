// Bringing units in from Strategic Reserves (see
// app/services/in_game/reinforcements.py, which decides when and where a
// unit can arrive). In their movement phase, from the second battle round, a
// player picks a unit in Reserves, clicks the board to set it down, arranges
// its models and brings it in - or, at the end of their opponent's movement
// phase, does the same with Rapid Ingress (1CP).

function ReservesPanel({ game, reserves, draft, checking, onSelectUnit, onPickUp, onBringIn }) {
  if (!reserves || reserves.seat === null || reserves.units.length === 0) return null
  const player = game.players.find((p) => p.seat === reserves.seat)
  const rapid = reserves.step === 'rapid_ingress'
  const selected = reserves.units.find((u) => u.unit_id === draft.unitId) ?? null
  const placed = selected && draft.kind === 'reinforce' && draft.positions !== null
  const check = draft.kind === 'reinforce' ? draft.check : null
  const where =
    reserves.battle_round === 2
      ? 'wholly within 6" of a battlefield edge, outside the enemy deployment zone'
      : 'wholly within 6" of a battlefield edge'

  return (
    <div className="deployment-panel">
      <h3>{rapid ? 'End of movement: Rapid Ingress' : 'Reserves'}</h3>
      <p>
        <strong>{player?.user_name}</strong>{' '}
        {rapid
          ? 'can use Rapid Ingress (1CP) to bring in a unit from Strategic Reserves.'
          : 'can bring in units from Strategic Reserves.'}{' '}
        <span className="hint">
          Each model {where} (anywhere, with Deep Strike), and at least 8" from every enemy model.
          {rapid ? '' : ' A unit brought in counts as having made a Normal move.'}
        </span>
      </p>
      <div className="radio-group">
        {reserves.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="reserve-unit"
              checked={draft.kind === 'reinforce' && draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit.unit_id)}
            />
            {unit.name}
            {unit.deep_strike && <span className="hint"> · Deep Strike</span>}
          </label>
        ))}
      </div>
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to bring in.</p>}
        {selected && !placed && (
          <p className="hint">Click the board where {selected.name} should arrive.</p>
        )}
        {placed && <p className="hint">Drag the models into place.</p>}
        {placed && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {placed && check?.valid && <p className="deployment-ready">Ready to bring in.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!placed || !check?.valid || checking} onClick={onBringIn}>
          {rapid ? 'Rapid Ingress (1CP)' : selected ? `Bring in ${selected.name}` : 'Bring in'}
        </button>
        <button type="button" disabled={!placed} onClick={onPickUp}>
          Pick up
        </button>
      </div>
    </div>
  )
}

export default ReservesPanel
