// Moving after shooting (see app/services/in_game/shoot_scoot.py): in the
// Shooting phase, a unit with an ability that lets it (e.g. Ride the
// Thermals) can make a Normal move once it has shot, if it isn't within
// Engagement Range. Pick it, drag its models, save the move.

function ShootScootPanel({ shooting, draft, checking, onPick, onSave }) {
  const units = (shooting?.units ?? []).filter((u) => u.shoot_scoot)
  if (units.length === 0) return null
  return (
    <div className="deployment-panel">
      <h3>Move after shooting</h3>
      <ul className="round-start-rules">
        {units.map((unit) => {
          const picked = draft.kind === 'scoot' && draft.unitId === unit.unit_id
          return (
            <li key={unit.unit_id}>
              <strong>{unit.name}</strong>
              <span className="hint">
                {' '}
                · {unit.shoot_scoot}, up to {unit.shoot_scoot_reach}"
              </span>
              <div className="inline-controls">
                <button type="button" onClick={() => onPick(unit)}>
                  {picked ? 'Moving…' : 'Move'}
                </button>
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

export default ShootScootPanel
