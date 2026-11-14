import { useState } from 'react'
import { decideAttack } from '../api'
import CombatResults from './CombatResults'

// An attack waiting on a player's decision as it's made (see
// app/services/in_game/attack_decisions.py) - the defender's: an Act of
// Faith for a saving throw, or Artisan / Necromechanic as one fails. Nothing
// else happens until they decide; the attack's then made with it (the same
// dice), up to its next decision or its result - shown here.

function outcomeOf(result) {
  const out = result.shot ?? result.fight
  return out && !out.pending ? out : null
}

function AttackDecisionPanel({ game, onChange, onError }) {
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const decision = game.pending_decision

  if (!decision && !outcome) return null

  const decide = async (option) => {
    setBusy(true)
    onError(null)
    try {
      const result = await decideAttack(game.id, { seat: decision.seat, choice: option.id })
      setOutcome(outcomeOf(result))
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="deployment-panel">
      {decision ? (
        <>
          <h3>Player {decision.seat}'s decision</h3>
          <p className="hint">
            {decision.kind === 'fight' ? 'A fight' : 'A shot'} is waiting on it - nothing
            else happens until it's made.
          </p>
          <p>{decision.prompt}</p>
          <div className="inline-controls">
            {decision.options.map((option) => (
              <button
                key={option.id}
                type="button"
                disabled={busy}
                onClick={() => decide(option)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="shooting-outcome">
          <h4>
            The attack, made{' '}
            <button type="button" onClick={() => setOutcome(null)}>
              Dismiss
            </button>
          </h4>
          <CombatResults
            result={outcome.combat}
            showFnp={outcome.combat.weapon_results.some((wr) => wr.fnp_rolls.length > 0)}
          />
          {(outcome.split_combats ?? []).map((s) => (
            <div key={s.unit_id}>
              <h4>… and {s.name}</h4>
              <CombatResults
                result={s.combat}
                showFnp={s.combat.weapon_results.some((wr) => wr.fnp_rolls.length > 0)}
              />
            </div>
          ))}
          {outcome.destroyed_unit_model_ids.length > 0 && (
            <p>
              <strong>{outcome.destroyed_unit_model_ids.length}</strong>{' '}
              {outcome.destroyed_unit_model_ids.length === 1 ? 'model' : 'models'} destroyed
              and removed from the battlefield.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default AttackDecisionPanel
