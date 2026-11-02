// Abilities declared during a phase or turn that happen at its end: by
// default Resurrection Orbs (see app/seeds/factions/necrons/reanimation.py)
// - once a battle, a unit with one can resurrect at the end of any phase,
// healing D6 wounds. Its player declares it (and can take it back). With
// other labels, the same for e.g. Tunnelling Horrors (into Strategic
// Reserves at the end of the opponent's turn).

function ResurrectionPanel({
  game,
  resurrection,
  onDeclare,
  title = 'Resurrection Orb',
  declaredText = 'resurrects at the end of this phase',
  declareLabel = 'Resurrect at the end of this phase',
}) {
  if (!resurrection || resurrection.units.length === 0) return null
  return (
    <div className="deployment-panel">
      <h4>{title}</h4>
      <ul className="round-start-rules">
        {resurrection.units.map((unit) => (
          <li key={unit.unit_id}>
            <strong>{unit.name}</strong>
            <span className="hint">
              {' '}
              · {game.players.find((p) => p.seat === unit.seat)?.user_name}
              {unit.declared ? ` · ${declaredText}` : ''}
            </span>
            <div className="inline-controls">
              <button type="button" onClick={() => onDeclare(unit, unit.declared)}>
                {unit.declared ? 'Take back' : declareLabel}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ResurrectionPanel
