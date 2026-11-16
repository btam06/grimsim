import { useState } from 'react'
import { decideAttack } from '../api'
import CombatResults from './CombatResults'

// An attack waiting on a player's decision as it's made (see
// app/services/in_game/attack_decisions.py): once rolls are made (a
// weapon's Hit, Wound or saving throws, its Attacks, a Damage or hazard
// roll), what can re-roll or change one (Command Re-roll, Seething Hatred,
// Artisan...) - the dice shown, then a
// row of them to pick from for each; an Act of Faith for a saving throw;
// Necromechanic as one fails. Nothing else happens until they decide; the
// attack's then made with it (the same dice), up to its next decision or
// its result - shown here.

const DIE_FACES = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅']
const ROLLS = {
  hit: 'Hit rolls',
  wound: 'Wound rolls',
  save: 'Saving throws',
  damage: 'Damage roll',
  hazard: 'Hazard roll',
  attacks: 'Attacks roll',
}

// The dice's options ("<source>:<dice index>"), grouped by source: [{ name,
// options: [{ option, index }] }], in order - and the rest (e.g. Carry on).
function bySource(options) {
  const sources = []
  const rest = []
  for (const option of options) {
    const match = /^(.+):(\d+)$/.exec(option.id)
    if (!match) {
      rest.push(option)
      continue
    }
    let source = sources.find((s) => s.id === match[1])
    if (!source) {
      source = {
        id: match[1],
        name: option.label.split(': ')[0],
        verb: match[1] === 'six' ? 'make it a 6' : 're-roll',
        options: [],
      }
      sources.push(source)
    }
    source.options.push({ option, index: Number(match[2]) })
  }
  return { sources, rest }
}

function RolledDice({ dice }) {
  return (
    <div className="rolled-dice">
      {dice.map((die, i) => (
        <span
          key={i}
          className={`rolled-die ${die.passed ? 'passed' : 'failed'}`}
          title={`Dice ${i + 1}: ${die.value} - ${die.passed ? 'succeeds' : 'fails'}${
            die.rerolled ? ' (re-rolled already)' : !die.rerollable ? " (can't be re-rolled)" : ''
          }`}
        >
          <span className="die-face">{DIE_FACES[die.value - 1] ?? die.value}</span>
          <small>{i + 1}{die.rerolled ? ' ↻' : ''}</small>
        </span>
      ))}
    </div>
  )
}

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
          {decision.type === 'reroll_dice' ? (
            <DiceChoice decision={decision} busy={busy} decide={decide} />
          ) : (
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
          )}
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

// A weapon's rolls made together: the dice, then for each thing that can
// re-roll or change one, the failed dice it could - pick one, or carry on.
function DiceChoice({ decision, busy, decide }) {
  const { sources, rest } = bySource(decision.options)
  return (
    <>
      <h4>{ROLLS[decision.roll] ?? 'Rolls'}</h4>
      <RolledDice dice={decision.dice} />
      {sources.map((source) => (
        <div key={source.id} className="inline-controls">
          <span>
            {source.name} - {source.verb}:
          </span>
          {source.options.map(({ option, index }) => (
            <button
              key={option.id}
              type="button"
              disabled={busy}
              title={option.label}
              onClick={() => decide(option)}
            >
              <span className="die-face">
                {DIE_FACES[decision.dice[index].value - 1] ?? decision.dice[index].value}
              </span>{' '}
              dice {index + 1}
            </button>
          ))}
        </div>
      ))}
      <div className="inline-controls">
        {rest.map((option) => (
          <button key={option.id} type="button" disabled={busy} onClick={() => decide(option)}>
            {option.label}
          </button>
        ))}
      </div>
    </>
  )
}

export default AttackDecisionPanel
