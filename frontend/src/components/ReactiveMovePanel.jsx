// Reactive moves (see app/services/in_game/reactive_move.py): in the
// opponent's Movement phase, a unit with an ability that lets it (e.g.
// Tactica Obliqua) can move once an enemy unit ends a move near it - roll for
// how far, drag its models, save the move.

function ReactiveMovePanel({ game, moves, draft, checking, onRoll, onPick, onSave }) {
  if (!moves || moves.length === 0) return null
  const name = (seat) => game.players.find((p) => p.seat === seat)?.user_name ?? `Seat ${seat}`
  return (
    <div className="deployment-panel">
      <h3>Reactive moves</h3>
      <ul className="round-start-rules">
        {moves.map((m) => {
          const picked = draft.kind === 'react' && draft.unitId === m.unit_id
          const reach = m.roll === null ? null : Math.max(m.roll, m.further ?? 0)
          return (
            <li key={m.unit_id}>
              <strong>{m.name}</strong>
              <span className="hint">
                {' '}
                · {name(m.seat)} · {m.ability}, after {m.trigger_name} moved
                {m.roll !== null && ` · rolled ${m.roll}"`}
                {m.roll !== null && m.further && m.further > m.roll
                  ? ` (or ${m.further}" ending near a friendly unit)`
                  : ''}
              </span>
              <div className="inline-controls">
                {m.roll === null ? (
                  <button type="button" onClick={() => onRoll(m)}>
                    Roll
                  </button>
                ) : (
                  <button type="button" onClick={() => onPick(m, reach)}>
                    {picked ? 'Moving…' : 'Move'}
                  </button>
                )}
                {picked && (
                  <button
                    type="button"
                    disabled={checking || !draft.check?.valid}
                    onClick={onSave}
                  >
                    Save move
                  </button>
                )}
              </div>
              {picked && draft.check && !draft.check.valid && (
                <p className="error">{draft.check.problems.join('; ')}</p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default ReactiveMovePanel
