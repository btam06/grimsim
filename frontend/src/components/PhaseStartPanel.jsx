// Abilities for the start of an opponent's phase (see
// app/services/in_game/phase_start.py) - e.g. Defend the Divine Work: at the
// start of their opponent's Shooting or Fight phase, the player can use it
// (once a battle) - or say they're done. The game waits for them first.

function PhaseStartPanel({ game, phaseStart, onUse, onDone }) {
  if (!phaseStart) return null
  const used = phaseStart.used ?? []
  if (phaseStart.seat == null) {
    if (used.length === 0) return null
    return (
      <div className="deployment-panel">
        <p className="hint">
          This phase:{' '}
          {used.map((u) => `${u.ability} (${u.unit_name})`).join(', ')}
        </p>
      </div>
    )
  }
  const player = game.players.find((p) => p.seat === phaseStart.seat)
  return (
    <div className="deployment-panel">
      <h3>Start of the {phaseStart.phase} phase</h3>
      <p>
        <strong>{player?.user_name}</strong> can use these before anything else happens in the
        phase.
      </p>
      <ul className="round-start-rules">
        {phaseStart.abilities.map((a) => (
          <li key={`${a.unit_id}-${a.ability}`}>
            <strong>{a.ability}</strong> · {a.unit_name}
            {a.description && <div className="hint">{a.description}</div>}
            <div className="inline-controls">
              <button type="button" onClick={() => onUse(phaseStart.seat, a)}>
                Use
              </button>
            </div>
          </li>
        ))}
      </ul>
      <div className="inline-controls">
        <button type="button" onClick={() => onDone(phaseStart.seat)}>
          Done
        </button>
      </div>
    </div>
  )
}

export default PhaseStartPanel
