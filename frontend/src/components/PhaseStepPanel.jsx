import ActivationButtons from './ActivationButtons'

// A phase's start or end step (see app/services/in_game/phase_start.py and
// phase_end.py): the player it's waiting on uses what they have for the start
// (or end) of the phase - e.g. Defend the Divine Work, Harbinger of Despair,
// Lord of the Storm - or says they're done. Nothing else happens in the phase
// till then; once they're all done with its end, the phase ends.

const PHASE_NAMES = {
  command: 'Command',
  movement: 'Movement',
  shooting: 'Shooting',
  charge: 'Charge',
  fight: 'Fight',
}

function PhaseStepPanel({ game, step, state, busy = false, onUse, onActivate, onDone }) {
  if (!state) return null
  const used = state.used ?? []
  if (state.seat == null) {
    if (step !== 'start' || used.length === 0) return null
    return (
      <div className="deployment-panel">
        <p className="hint">
          This phase: {used.map((u) => `${u.ability} (${u.unit_name})`).join(', ')}
        </p>
      </div>
    )
  }
  const player = game.players.find((p) => p.seat === state.seat)
  const abilities = state.abilities ?? []
  const activations = (state.activations ?? []).filter((a) => a.seat === state.seat)
  const phase = PHASE_NAMES[state.phase] ?? state.phase
  return (
    <div className="deployment-panel">
      <h3>
        {step === 'start' ? 'Start' : 'End'} of the {phase} phase
      </h3>
      <p>
        <strong>{player?.user_name}</strong>{' '}
        {step === 'start'
          ? 'can use these before anything else happens in the phase.'
          : 'can use or declare these before the phase ends.'}
      </p>
      <ul className="round-start-rules">
        {abilities.map((a) => (
          <li key={`${a.unit_id}-${a.ability}`}>
            <strong>{a.ability}</strong> · {a.unit_name}
            {a.description && <div className="hint">{a.description}</div>}
            <div className="inline-controls">
              <button type="button" disabled={busy} onClick={() => onUse(state.seat, a)}>
                Use
              </button>
            </div>
          </li>
        ))}
        {activations.map((a) => (
          <li key={`${a.unit_id}:${a.ability}`}>
            <strong>{a.ability}</strong> · {a.name}
            {a.description && <div className="hint">{a.description}</div>}
            <ActivationButtons activation={a} busy={busy} onActivate={onActivate} />
          </li>
        ))}
      </ul>
      {step === 'end' && abilities.length === 0 && activations.length === 0 && (
        <p className="hint">Declare Resurrection Orbs or end-of-turn Reserves below, if any.</p>
      )}
      <div className="inline-controls">
        <button type="button" disabled={busy} onClick={() => onDone(state.seat)}>
          Done
        </button>
      </div>
    </div>
  )
}

export default PhaseStepPanel
