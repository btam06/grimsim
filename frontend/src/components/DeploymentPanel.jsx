// Setting up the armies before the first battle round (see
// app/services/in_game/deployment.py, which decides everything here: whose turn it is,
// where a unit's models start, and whether they can be set up where they are).
// The player picks a unit, clicks the board to set it down, drags its models
// into place, and deploys it.

const sideName = (game, seat) => (seat === game.attacker_seat ? 'Attacker' : 'Defender')

function DeploymentPanel({ game, deployment, draft, checking, onSelectUnit, onPickUp, onDeploy }) {
  if (!deployment) return null
  const seat = deployment.deploying_seat
  const player = game.players.find((p) => p.seat === seat)
  const left = (s) =>
    deployment.units.filter((u) => u.seat === s && !u.deployed && !u.formation).length
  // Not in Strategic Reserves or embarked (they aren't deployed).
  const units = deployment.units.filter((u) => u.seat === seat && !u.deployed && !u.formation)
  const setAside = deployment.units.filter((u) => u.seat === seat && u.formation)
  const selected = units.find((u) => u.unit_id === draft.unitId) ?? null
  const placed = selected && draft.positions !== null
  const check = draft.check

  return (
    <div className="deployment-panel">
      <h3>Deployment</h3>
      <p>
        <strong>{player?.user_name}</strong> ({sideName(game, seat)}) sets up a unit.{' '}
        <span className="hint">
          {game.players
            .map((p) => `${p.user_name}: ${left(p.seat)} left`)
            .join(' · ')}
        </span>
      </p>
      <div className="radio-group">
        {units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="deploy-unit"
              checked={draft.unitId === unit.unit_id}
              onChange={() => onSelectUnit(unit.unit_id)}
            />
            {unit.name}
            <span className="hint">
              {' '}
              · {unit.models.length} {unit.models.length === 1 ? 'model' : 'models'}
              {unit.infiltrators ? ' · Infiltrators' : ''}
            </span>
          </label>
        ))}
      </div>

      {setAside.length > 0 && (
        <p className="hint">
          Not deployed:{' '}
          {setAside
            .map((u) => {
              if (u.formation === 'reserves') return `${u.name} (Strategic Reserves)`
              const transport = deployment.units.find((t) => t.unit_id === u.transport_unit_id)
              return `${u.name} (embarked in ${transport?.name ?? 'a transport'})`
            })
            .join(', ')}
        </p>
      )}

      {/* A fixed height (scrolling if need be), so the board below doesn't
          jump as the check's problems come and go. */}
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to set up.</p>}
        {selected && !placed && (
          <p className="hint">
            Click the board where {selected.name} should go
            {selected.infiltrators
              ? ' - in your deployment zone, or more than 9" from the enemy\'s and their models.'
              : ' - in your deployment zone.'}
          </p>
        )}
        {placed && (
          <p className="hint">
            Drag the models into place: each within 9" of every other model in the unit and
            within 2" of at least one of them.
          </p>
        )}
        {placed && check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {placed && check?.valid && <p className="deployment-ready">Ready to deploy.</p>}
        {selected?.models.some((m) => !m.measured) && (
          <p className="hint">
            Some of its models have no measured base, so they're shown as 32mm.
          </p>
        )}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!placed || !check?.valid || checking} onClick={onDeploy}>
          {selected ? `Deploy ${selected.name}` : 'Deploy'}
        </button>
        <button type="button" disabled={!placed} onClick={onPickUp}>
          Pick up
        </button>
      </div>
    </div>
  )
}

export default DeploymentPanel
