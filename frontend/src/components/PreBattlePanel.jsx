// Once everything is set up, the players roll off for who goes first (each
// rolls a D6, the highest goes first, ties re-roll - see
// app/services/in_game/first_turn.py); then, at the start of the first battle
// round, they make Scouts moves (see scouts.py) - the player going first,
// then their opponent: each unit whose every model has Scouts can make a
// Normal move of up to that far. Pick a unit, drag its models, save the move;
// say when you're done.

function rollsByAttempt(rolls) {
  const attempts = {}
  for (const r of rolls) {
    attempts[r.attempt] = { ...attempts[r.attempt], [r.seat]: r.roll }
  }
  return Object.entries(attempts)
}

function PreBattlePanel({ game, scouts, draft, checking, onRoll, onPick, onSave, onDone }) {
  const name = (seat) => game.players.find((p) => p.seat === seat)?.user_name ?? `Seat ${seat}`
  const rolls = rollsByAttempt(game.first_turn_rolls ?? [])
  const picked = scouts?.units.find((u) => u.unit_id === draft.unitId && draft.kind === 'scout')
  return (
    <div className="deployment-panel">
      <h3>{game.deployment_step === 'first_turn' ? 'Who goes first' : 'Scouts moves'}</h3>
      {game.deployment_step === 'first_turn' ? (
        <>
          <p className="hint">
            Everything is set up. Roll off for who goes first: the highest roll goes first, and a
            tie is re-rolled.
          </p>
          <button type="button" onClick={onRoll}>
            Roll off
          </button>
        </>
      ) : (
        <p>
          <strong>{name(game.first_seat)}</strong> goes first.
        </p>
      )}
      {rolls.length > 0 && (
        <ul className="hint">
          {rolls.map(([attempt, r]) => (
            <li key={attempt}>
              {name(1)} {r[1]} · {name(2)} {r[2]}
              {r[1] === r[2] ? ' — tie, re-rolled' : ''}
            </li>
          ))}
        </ul>
      )}
      {game.status === 'in_progress' && scouts?.seat && (
        <div>
          <h4>Scouts moves: {name(scouts.seat)}</h4>
          <ul className="round-start-rules">
            {scouts.units.map((unit) => (
              <li key={unit.unit_id}>
                <strong>{unit.name}</strong>
                <span className="hint">
                  {' '}
                  · Scouts {unit.distance}"{unit.moved ? ' · moved' : ''}
                </span>
                <div className="inline-controls">
                  <button type="button" onClick={() => onPick(unit)}>
                    {picked?.unit_id === unit.unit_id ? 'Moving…' : 'Move'}
                  </button>
                  {picked?.unit_id === unit.unit_id && (
                    <button
                      type="button"
                      disabled={checking || !draft.check?.valid}
                      onClick={onSave}
                      title={draft.check?.problems?.join('; ') ?? ''}
                    >
                      Save move
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {picked && draft.check && !draft.check.valid && (
            <p className="error">{draft.check.problems.join('; ')}</p>
          )}
          <div className="inline-controls">
            <button type="button" onClick={() => onDone(scouts.seat)}>
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default PreBattlePanel
