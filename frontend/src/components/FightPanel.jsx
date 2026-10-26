import { useEffect, useState } from 'react'
import { fight, getFightTargets } from '../api'
import CombatResults from './CombatResults'
import { onePerProfile, otherProfile } from '../weaponProfiles'

// Fighting, once both players have piled in (see
// app/services/in_game/fighting.py, which decides who picks the next unit to
// fight and what it can reach, and app/services/combat.py, which resolves
// it). Units with Fights First (those that charged this turn, or whose every
// model has it) fight first; the players take turns to pick a unit.

const STEP_NAMES = {
  consolidate: 'Consolidate',
  fights_first: 'Fights First',
  remaining: 'Remaining combatants',
  done: 'All fights done',
}

function unitStatus(unit) {
  if (unit.fought) return 'Fought'
  const tags = []
  if (unit.fights_first) tags.push(unit.charged ? 'Fights First (charged)' : 'Fights First')
  if (!unit.can_fight) tags.push(unit.reason)
  return tags.join(' · ') || 'Can fight'
}

// The unit that's just fought can consolidate: each model up to 3", towards
// the unit it fought (or, if that's gone, the nearest enemy), ending within
// Engagement Range of an enemy unit - or not at all.
function Consolidation({ player, consolidating, draft, checking, onConsolidate, onReset, onSkip }) {
  const { unit_name: name, target_name: target, target_destroyed: destroyed } = consolidating
  const check = draft.kind === 'consolidate' ? draft.check : null
  return (
    <>
      <p>
        <strong>{player?.user_name}</strong>: {name} can consolidate.{' '}
        <span className="hint">
          Each model up to 3"
          {destroyed
            ? `, towards the nearest enemy (${target} is destroyed), ending within Engagement Range of another unit - or onto an objective`
            : ` towards ${target}, staying within Engagement Range`}
          . A unit it ends up engaged with that hasn't fought can then fight.
        </span>
      </p>
      <div className="deployment-status">
        {check && !check.valid && (
          <ul className="deployment-problems">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        {check?.valid && <p className="deployment-ready">Ready to consolidate.</p>}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={!check?.valid || checking} onClick={onConsolidate}>
          Consolidate {name}
        </button>
        <button type="button" onClick={onReset}>
          Reset
        </button>
        <button type="button" onClick={onSkip}>
          Don't consolidate
        </button>
      </div>
    </>
  )
}

function FightPanel({
  game,
  fightState,
  focus,
  onFocus,
  onFought,
  onError,
  draft,
  checking,
  onConsolidate,
  onResetConsolidation,
  onSkipConsolidation,
}) {
  const [targets, setTargets] = useState([])
  const [weaponIds, setWeaponIds] = useState(new Set())
  const [outcome, setOutcome] = useState(null)
  const [busy, setBusy] = useState(false)
  const selected = fightState?.units.find((u) => u.unit_id === focus.unitId) ?? null
  const target = targets.find((t) => t.unit_id === focus.targetId) ?? null
  const key = (w) => `${w.enhancement ? 'e' : 'w'}${w.id}`

  // The selected unit's targets, while it can fight.
  useEffect(() => {
    setTargets([])
    if (!selected?.can_fight) return
    let cancelled = false
    getFightTargets(game.id, selected.unit_id)
      .then((t) => !cancelled && setTargets(t))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, selected?.unit_id, selected?.can_fight])

  // Picking a target picks each model's first melee weapon that can reach.
  useEffect(() => {
    setWeaponIds(
      new Set(
        onePerProfile((target?.weapons ?? []).filter((w) => w.in_range && w.default)).map(key)
      )
    )
  }, [target])

  if (!fightState) return null
  const player = game.players.find((p) => p.seat === fightState.seat)
  const step = fightState.step

  const go = async () => {
    setBusy(true)
    onError(null)
    try {
      const chosen = target.weapons.filter((w) => weaponIds.has(key(w)))
      const result = await fight(game.id, {
        unit_id: selected.unit_id,
        target_unit_id: target.unit_id,
        weapon_ids: chosen.filter((w) => !w.enhancement).map((w) => w.id),
        enhancement_weapon_ids: chosen.filter((w) => w.enhancement).map((w) => w.id),
      })
      setOutcome({ unit: selected.name, target: target.name, ...result })
      onFocus({ unitId: null, targetId: null })
      onFought()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // Picking one profile of a weapon unpicks its others.
  const toggle = (w) =>
    setWeaponIds((ids) => {
      const next = new Set(ids)
      if (next.has(key(w))) next.delete(key(w))
      else {
        next.add(key(w))
        for (const other of target.weapons) {
          if (otherProfile(w.name, other.name)) next.delete(key(other))
        }
      }
      return next
    })

  const sides = [game.turn_seat, game.players.find((p) => p.seat !== game.turn_seat)?.seat]
  return (
    <div className="deployment-panel">
      <h3>Fight · {STEP_NAMES[step] ?? step}</h3>
      {step !== 'done' && step !== 'consolidate' && (
        <p>
          <strong>{player?.user_name}</strong> picks a unit to fight.{' '}
          <span className="hint">Players take turns; Fights First units go before the rest.</span>
        </p>
      )}
      {step === 'consolidate' && fightState.consolidating && (
        <Consolidation
          player={player}
          consolidating={fightState.consolidating}
          draft={draft}
          checking={checking}
          onConsolidate={onConsolidate}
          onReset={onResetConsolidation}
          onSkip={onSkipConsolidation}
        />
      )}
      {sides.map((seat) => {
        const owner = game.players.find((p) => p.seat === seat)
        const units = fightState.units.filter((u) => u.seat === seat)
        return (
          <div key={seat}>
            <h4>
              {owner?.user_name}
              {seat === game.turn_seat ? ' (their turn)' : ''}
            </h4>
            <div className="radio-group">
              {units.map((unit) => (
                <label key={unit.unit_id} className="radio-option">
                  <input
                    type="radio"
                    name="fight-unit"
                    disabled={!unit.can_fight}
                    checked={focus.unitId === unit.unit_id}
                    onChange={() => {
                      setOutcome(null)
                      onFocus({ unitId: unit.unit_id, targetId: null })
                    }}
                  />
                  {unit.name}
                  <span className="hint"> · {unitStatus(unit)}</span>
                </label>
              ))}
            </div>
          </div>
        )
      })}

      {selected?.can_fight && (
        <>
          <h4>Target</h4>
          <div className="radio-group">
            {targets.map((t) => (
              <label key={t.unit_id} className="radio-option">
                <input
                  type="radio"
                  name="fight-target"
                  checked={focus.targetId === t.unit_id}
                  onChange={() => onFocus({ ...focus, targetId: t.unit_id })}
                />
                {t.name}
              </label>
            ))}
          </div>
        </>
      )}

      {selected?.can_fight && target && (
        <>
          <h4>Melee weapons</h4>
          <div className="radio-group">
            {target.weapons.map((w) => (
              <label key={key(w)} className="radio-option">
                <input
                  type="checkbox"
                  disabled={!w.in_range}
                  checked={weaponIds.has(key(w))}
                  onChange={() => toggle(w)}
                />
                {w.name}
                <span className="hint">
                  {' '}
                  · {w.in_range} of {w.carried_by} within Engagement Range
                </span>
              </label>
            ))}
            {target.weapons.length === 0 && <p className="hint">It has no melee weapons.</p>}
          </div>
          <div className="inline-controls">
            <button type="button" disabled={busy || weaponIds.size === 0} onClick={go}>
              Fight {target.name}
            </button>
          </div>
        </>
      )}

      {outcome && (
        <div className="shooting-outcome">
          <h4>
            {outcome.unit} fought {outcome.target}
            {outcome.charged ? ' (charged)' : ''}
          </h4>
          <CombatResults
            result={outcome.combat}
            showFnp={outcome.combat.weapon_results.some((wr) => wr.fnp_rolls.length > 0)}
          />
          {outcome.destroyed_unit_model_ids.length > 0 && (
            <p>
              <strong>{outcome.destroyed_unit_model_ids.length}</strong>{' '}
              {outcome.destroyed_unit_model_ids.length === 1 ? 'model' : 'models'} destroyed
              and removed from the battlefield (in this game only).
            </p>
          )}
        </div>
      )}

      {fightState.fights.length > 0 && (
        <>
          <h4>Fought so far</h4>
          <ol className="hint">
            {fightState.fights.map((f, i) => (
              <li key={i}>
                {f.unit_name} → {f.target_name}
                {f.fights_first ? ' (Fights First)' : ''}: {f.total_damage} damage,{' '}
                {f.models_destroyed} destroyed
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

export default FightPanel
