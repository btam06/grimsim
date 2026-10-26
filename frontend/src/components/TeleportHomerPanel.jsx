// Teleport Homers (see app/seeds/factions/space_marines/teleport_homer.py): at the start
// of the battle, each player can set up one token for each of their units
// with a Teleport Homer, anywhere on the battlefield - pick a unit, then click
// the board - and says when they're done. The game waits until both are.

function TeleportHomerPanel({ game, homers, placingUnitId, onPick, onRemove, onDone }) {
  if (!homers || homers.waiting_seats.length === 0) return null
  return (
    <div className="deployment-panel">
      <h3>Start of the battle: Teleport Homers</h3>
      <p className="hint">
        Each unit with a Teleport Homer can set up one token anywhere on the battlefield. An enemy
        unit ending a move within 1" of it removes it; Rapid Ingress can use it (1CP less) to set
        the unit up within 3" of it.
      </p>
      {homers.waiting_seats.map((seat) => (
        <div key={seat}>
          <h4>{game.players.find((p) => p.seat === seat)?.user_name}</h4>
          <ul className="round-start-rules">
            {homers.units
              .filter((u) => u.seat === seat)
              .map((unit) => (
                <li key={unit.unit_id}>
                  <strong>{unit.name}</strong>
                  <span className="hint">
                    {' '}
                    ·{' '}
                    {unit.token
                      ? `token at (${unit.token.x.toFixed(1)}, ${unit.token.y.toFixed(1)})`
                      : 'no token'}
                  </span>
                  <div className="inline-controls">
                    <button type="button" onClick={() => onPick(seat, unit.unit_id)}>
                      {placingUnitId === unit.unit_id
                        ? 'Click the board…'
                        : unit.token
                          ? 'Move token'
                          : 'Set up token'}
                    </button>
                    {unit.token && (
                      <button type="button" onClick={() => onRemove(seat, unit.unit_id)}>
                        Remove
                      </button>
                    )}
                  </div>
                </li>
              ))}
          </ul>
          <div className="inline-controls">
            <button type="button" onClick={() => onDone(seat)}>
              Done
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default TeleportHomerPanel
