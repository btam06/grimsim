// Reanimation Protocols, at the end of the command phase (see
// app/seeds/factions/necrons/reanimation.py, which heals each unit, and
// app/services/in_game/heal.py, which decides where returned models can go).
// Each unit with the ability healed D3 wounds:
// a wounded model regains a wound, or a destroyed one returns with 1 wound -
// and the player whose turn it is sets each returned model up, in coherency
// with its unit and out of Engagement Range, before moving on.

function rollText(unit) {
  const parts = []
  if (unit.healed) parts.push(`${unit.healed} ${unit.healed === 1 ? 'wound' : 'wounds'} healed`)
  if (unit.returned) {
    parts.push(`${unit.returned} ${unit.returned === 1 ? 'model' : 'models'} returned`)
  }
  return `rolled ${unit.roll}: ${parts.join(', ') || 'nothing to heal'}`
}

function ReanimationPanel({ game, reanimation, draft, checking, onSelectUnit, onPlace }) {
  if (!reanimation?.placing) return null
  const player = game.players.find((p) => p.seat === reanimation.seat)
  const selected =
    draft.kind === 'reanimate'
      ? (reanimation.units.find((u) => u.unit_id === draft.unitId) ?? null)
      : null
  const check = selected ? draft.check : null

  return (
    <div className="deployment-panel">
      <h3>End of command: Reanimation Protocols</h3>
      <p>
        <strong>{player?.user_name}</strong> sets up their reanimated models.{' '}
        <span className="hint">
          Each in coherency with its unit, and not within Engagement Range of an enemy model.
        </span>
      </p>
      <div className="radio-group">
        {reanimation.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="reanimate-unit"
              disabled={unit.to_place.length === 0}
              checked={selected?.unit_id === unit.unit_id}
              onChange={() => onSelectUnit(unit)}
            />
            {unit.name}
            <span className="hint">
              {' '}
              · {rollText(unit)}
              {unit.returned > 0 && unit.to_place.length === 0 && ' · set up'}
            </span>
          </label>
        ))}
      </div>
      <div className="deployment-status">
        {!selected && <p className="hint">Choose a unit to set up its returned models.</p>}
        {selected && <p className="hint">Drag the returned models into place.</p>}
        {check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {check?.valid && <p className="deployment-ready">Ready to set up.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!check?.valid || checking} onClick={onPlace}>
          {selected ? `Set up ${selected.name}'s returned models` : 'Set up'}
        </button>
      </div>
    </div>
  )
}

export default ReanimationPanel
