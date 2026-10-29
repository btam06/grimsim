import { useEffect, useState } from 'react'
import { fight, getFightTargets, passFight } from '../api'
import AllocationOrder from './AllocationOrder'
import CombatResults from './CombatResults'
import { onePerProfile, otherProfile } from '../weaponProfiles'

// Fighting, once both players have piled in (see
// app/services/in_game/fighting.py, which decides who picks the next unit to
// fight and what it can reach, and app/services/combat.py, which resolves
// it). Units eligible to fight are listed (engaged, engaged at the start of
// the Fight step, or that charged), and those that have fought. Units with
// Fights First (those that charged this turn, or whose every model has it)
// fight first; the players take turns to pick a unit. One that's eligible
// but not engaged when it's picked makes an overrun fight's pile-in first. A
// player whose eligible units are all more than 5" from the enemy can pass.
// Each model fights with one melee weapon (and every [EXTRA ATTACKS] one);
// a weapon's attacks can be split between the units it's engaged with. Once
// the fighting's done, the units that fought consolidate - the player whose
// turn it is first, in any order they like.

const STEP_NAMES = {
  fights_first: 'Fights First',
  remaining: 'Remaining combatants',
  consolidate: 'Consolidate',
  done: 'All fights done',
}

const MODE_HINTS = {
  ongoing:
    'Ongoing consolidation: models in base contact stay put; each other model ends closer to the closest enemy unit it\'s engaged with, and each model that started engaged stays engaged.',
  engaging:
    'Engaging consolidation: pick enemy units within 3" - the unit must end engaged with all of them (any that haven\'t fought then fight it).',
  objective:
    'Objective consolidation: pick an objective within 3" - each model that moves ends within range of it or closer, and the unit ends within range.',
}

function unitStatus(unit) {
  if (unit.fought) return 'Fought'
  const tags = []
  if (unit.fights_first) tags.push(unit.charged ? 'Fights First (charged)' : 'Fights First')
  if (unit.overrun) tags.push('not engaged: overrun pile-in first')
  else if (!unit.can_fight) tags.push(unit.reason)
  return tags.join(' · ') || 'Can fight'
}

// A unit that fought can consolidate in its mode (12.08): each model up to
// 3" - or not at all. Its player picks which of their units consolidates
// next, and for an engaging or objective consolidation, what it goes for.
function Consolidation({
  player,
  consolidations,
  consolidatingId,
  onPick,
  onPicks,
  draft,
  checking,
  onConsolidate,
  onReset,
  onSkip,
}) {
  const consolidating = consolidations.find((c) => c.unit_id === consolidatingId)
  if (!consolidating) return null
  const { unit_name: name, mode, options = [] } = consolidating
  const check = draft.kind === 'consolidate' ? draft.check : null
  const picks = draft.kind === 'consolidate' ? (draft.options?.pick_ids ?? []) : []
  // By default the first offered (the closest enemy unit).
  const picked = picks.length ? picks : options.slice(0, 1).map((o) => o.id)
  const toggle = (id) =>
    onPicks(
      mode === 'objective'
        ? [id]
        : picked.includes(id)
          ? picked.filter((p) => p !== id)
          : [...picked, id]
    )
  return (
    <>
      <p>
        <strong>{player?.user_name}</strong> consolidates their units that fought.{' '}
        <span className="hint">{MODE_HINTS[mode] ?? 'Each model up to 3".'}</span>
      </p>
      <div className="radio-group">
        {consolidations.map((c) => (
          <label key={c.unit_id} className="radio-option">
            <input
              type="radio"
              name="consolidating-unit"
              checked={c.unit_id === consolidatingId}
              onChange={() => onPick(c.unit_id)}
            />
            {c.unit_name}
            {c.unit_id === consolidatingId && <span className="selecting-tag"> · consolidating</span>}
            <span className="hint">
              {' '}
              · fought {c.target_name}
              {c.mode ? ` · ${c.mode}` : ''}
            </span>
          </label>
        ))}
      </div>
      {mode === 'ongoing' && options.length > 0 && (
        <p className="hint">Towards: {options.map((o) => o.name).join(', ')}</p>
      )}
      {(mode === 'engaging' || mode === 'objective') && (
        <>
          <h4>{mode === 'engaging' ? 'Enemy units to engage' : 'Objective'}</h4>
          <div className="radio-group">
            {options.map((o) => (
              <label key={o.id} className="radio-option">
                <input
                  type={mode === 'engaging' ? 'checkbox' : 'radio'}
                  name="consolidation-pick"
                  checked={picked.includes(o.id)}
                  onChange={() => toggle(o.id)}
                />
                {o.name}
              </label>
            ))}
          </div>
        </>
      )}
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

const key = (w) => `${w.enhancement ? 'e' : 'w'}${w.id}`
const fixedAttacks = (w) => (/^\d+$/.test(w.attacks ?? '') ? Number(w.attacks) : null)

// The unit's melee weapons across its targets (each target's list says how
// many of its models can reach that one): {key: {weapon, reach: {target id:
// models in range}}}.
function weaponsByKey(targets) {
  const found = {}
  for (const t of targets) {
    for (const w of t.weapons) {
      const entry = (found[key(w)] ??= { weapon: w, reach: {} })
      entry.reach[t.unit_id] = w.in_range
    }
  }
  return found
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
  consolidatingId,
  onPickConsolidation,
  onConsolidationPicks,
  onStartOverrun,
  onPileIn,
  onResetPileIn,
  onConsolidate,
  onResetConsolidation,
  onSkipConsolidation,
}) {
  const [targets, setTargets] = useState([])
  const [weaponIds, setWeaponIds] = useState(new Set())
  // Per weapon (key) split between targets: {key: {target id: attacks}}.
  const [splits, setSplits] = useState({})
  // The defender's allocation order for each target: {target id: [group ids]}.
  const [orders, setOrders] = useState({})
  const [outcome, setOutcome] = useState(null)
  const [busy, setBusy] = useState(false)
  const selected = fightState?.units.find((u) => u.unit_id === focus.unitId) ?? null
  const target = targets.find((t) => t.unit_id === focus.targetId) ?? null
  const weapons = weaponsByKey(targets)

  // The selected unit's targets, while it can fight.
  useEffect(() => {
    setTargets([])
    setSplits({})
    setOrders({})
    if (!selected?.can_fight) return
    let cancelled = false
    getFightTargets(game.id, selected.unit_id)
      .then((t) => !cancelled && setTargets(t))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, selected?.unit_id, selected?.can_fight])

  // Picking a target picks each model's first melee weapon that can reach it
  // (and every [EXTRA ATTACKS] weapon).
  useEffect(() => {
    setWeaponIds(
      new Set(
        onePerProfile((target?.weapons ?? []).filter((w) => w.in_range && w.default)).map(key)
      )
    )
    setSplits({})
  }, [target])

  if (!fightState) return null
  const player = game.players.find((p) => p.seat === fightState.seat)
  const step = fightState.step
  const defenderName = (t) =>
    game.players.find((p) => p.seat !== selected?.seat)?.user_name ?? t?.name

  const splitPayload = () =>
    Object.entries(splits).flatMap(([k, byTarget]) => {
      const { weapon } = weapons[k]
      return Object.entries(byTarget)
        .filter(([, n]) => n > 0)
        .map(([t, n]) => ({
          weapon_id: weapon.id,
          enhancement: weapon.enhancement,
          target_unit_id: Number(t),
          attacks: n,
        }))
    })

  const go = async () => {
    setBusy(true)
    onError(null)
    try {
      const chosen = Object.values(weapons)
        .map((e) => e.weapon)
        .filter((w) => weaponIds.has(key(w)) || w.extra_attacks)
      const result = await fight(game.id, {
        unit_id: selected.unit_id,
        target_unit_id: target.unit_id,
        weapon_ids: chosen.filter((w) => !w.enhancement).map((w) => w.id),
        enhancement_weapon_ids: chosen.filter((w) => w.enhancement).map((w) => w.id),
        splits: splitPayload(),
        allocation_order: orders[target.unit_id] ?? [],
        allocation_orders: Object.fromEntries(
          Object.entries(orders).filter(([t]) => Number(t) !== target.unit_id)
        ),
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

  const pass = async () => {
    onError(null)
    try {
      await passFight(game.id, { seat: fightState.seat })
      onFought()
    } catch (err) {
      onError(err.message)
    }
  }

  // Picking one profile of a weapon unpicks its others - and (04.01) any
  // other melee weapon carried by the same models isn't unpicked here: the
  // backend says if a model would have two.
  const toggle = (w) =>
    setWeaponIds((ids) => {
      const next = new Set(ids)
      if (next.has(key(w))) next.delete(key(w))
      else {
        next.add(key(w))
        for (const { weapon: other } of Object.values(weapons)) {
          if (otherProfile(w.name, other.name)) next.delete(key(other))
        }
      }
      return next
    })

  // Splitting a weapon's attacks: by default all against the target.
  const splitOf = (k) => splits[k] ?? null
  const startSplit = (k, w) => {
    const total = (fixedAttacks(w) ?? 0) * (weapons[k].reach[target.unit_id] ?? 0)
    setSplits((s) => ({ ...s, [k]: { [target.unit_id]: total } }))
  }
  const setSplit = (k, targetId, n) =>
    setSplits((s) => ({ ...s, [k]: { ...(s[k] ?? {}), [targetId]: Math.max(0, n) } }))
  const stopSplit = (k) =>
    setSplits((s) => {
      const next = { ...s }
      delete next[k]
      return next
    })
  // The targets any split puts attacks into (each needs an allocation order).
  const splitTargets = targets.filter(
    (t) =>
      t.unit_id !== target?.unit_id &&
      Object.values(splits).some((byTarget) => (byTarget[t.unit_id] ?? 0) > 0)
  )

  const pilingIn = draft.kind === 'pile_in'
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
      {fightState.can_pass && (
        <div className="inline-controls">
          <button type="button" onClick={pass}>
            Pass
          </button>
          <span className="hint">
            {' '}
            Every unit of {player?.user_name}'s eligible to fight is more than 5" from the enemy.
          </span>
        </div>
      )}
      {step === 'consolidate' && (
        <Consolidation
          player={player}
          consolidations={fightState.consolidations ?? []}
          consolidatingId={consolidatingId}
          onPick={onPickConsolidation}
          onPicks={onConsolidationPicks}
          draft={draft}
          checking={checking}
          onConsolidate={onConsolidate}
          onReset={onResetConsolidation}
          onSkip={onSkipConsolidation}
        />
      )}
      {step !== 'consolidate' && sides.map((seat) => {
        const owner = game.players.find((p) => p.seat === seat)
        const units = fightState.units.filter((u) => u.seat === seat)
        if (units.length === 0) return null
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
                  {focus.unitId === unit.unit_id && (
                    <span className="selecting-tag"> · selected</span>
                  )}
                  <span className="hint"> · {unitStatus(unit)}</span>
                  {unit.overrun && (
                    <button type="button" onClick={() => onStartOverrun(unit)}>
                      {pilingIn && draft.unitId === unit.unit_id ? 'Piling in…' : 'Pile in'}
                    </button>
                  )}
                </label>
              ))}
            </div>
          </div>
        )
      })}

      {pilingIn && (
        <>
          <p className="hint">
            Overrun fight (12.06): drag its models up to 3" towards an enemy unit within 5",
            ending engaged - then it fights.
          </p>
          {draft.check && !draft.check.valid && (
            <ul className="deployment-problems">
              {draft.check.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
          <div className="inline-controls">
            <button type="button" disabled={!draft.check?.valid || checking} onClick={onPileIn}>
              Pile in
            </button>
            <button type="button" onClick={onResetPileIn}>
              Reset
            </button>
          </div>
        </>
      )}

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
          <p className="hint">
            Each model fights with one melee weapon, and every [EXTRA ATTACKS] weapon it has.
          </p>
          <div className="radio-group">
            {Object.entries(weapons).map(([k, { weapon: w, reach }]) => {
              const split = splitOf(k)
              const attacks = fixedAttacks(w)
              const reachable = targets.filter((t) => (reach[t.unit_id] ?? 0) > 0)
              return (
                <div key={k}>
                  <label className="radio-option">
                    <input
                      type="checkbox"
                      disabled={w.extra_attacks || !reachable.length}
                      checked={w.extra_attacks || weaponIds.has(k)}
                      onChange={() => toggle(w)}
                    />
                    {w.name}
                    <span className="hint">
                      {' '}
                      · A {w.attacks || '?'}
                      {w.extra_attacks ? ' · [EXTRA ATTACKS]' : ''} · {reach[target.unit_id] ?? 0}{' '}
                      of {w.carried_by} engaged with {target.name}
                    </span>
                    {(weaponIds.has(k) || w.extra_attacks) &&
                      reachable.length > 1 &&
                      attacks !== null &&
                      (split ? (
                        <button type="button" onClick={() => stopSplit(k)}>
                          Don't split
                        </button>
                      ) : (
                        <button type="button" onClick={() => startSplit(k, w)}>
                          Split attacks
                        </button>
                      ))}
                  </label>
                  {split && (
                    <div className="split-attacks">
                      {reachable.map((t) => (
                        <label key={t.unit_id} className="radio-option">
                          {t.name}:{' '}
                          <input
                            type="number"
                            min={0}
                            max={attacks * (reach[t.unit_id] ?? 0)}
                            value={split[t.unit_id] ?? 0}
                            onChange={(e) => setSplit(k, t.unit_id, Number(e.target.value))}
                          />
                          <span className="hint"> of {attacks * (reach[t.unit_id] ?? 0)}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {targets.length > 0 && Object.keys(weapons).length === 0 && (
              <p className="hint">It has no melee weapons.</p>
            )}
          </div>
          {[target, ...splitTargets].map((t) => (
            <AllocationOrder
              key={t.unit_id}
              gameId={game.id}
              unitId={t.unit_id}
              defender={`${defenderName(t)} (${t.name})`}
              order={orders[t.unit_id] ?? []}
              onChange={(order) => setOrders((o) => ({ ...o, [t.unit_id]: order }))}
            />
          ))}
          <div className="inline-controls">
            <button
              type="button"
              disabled={
                busy ||
                (weaponIds.size === 0 &&
                  !Object.values(weapons).some((e) => e.weapon.extra_attacks))
              }
              onClick={go}
            >
              Fight {target.name}
              {splitTargets.length ? ` (and ${splitTargets.map((t) => t.name).join(', ')})` : ''}
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
