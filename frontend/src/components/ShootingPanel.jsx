import { useEffect, useState } from 'react'
import {
  fireOverwatch,
  getActions,
  getOverwatchTargets,
  getShootingTargets,
  shoot,
  startAction,
} from '../api'
import AllocationOrder from './AllocationOrder'
import CombatResults from './CombatResults'
import { onePerProfile, otherProfile } from '../weaponProfiles'

// Shooting in the shooting phase (see app/services/in_game/shooting.py, which decides
// what each unit can see and reach, and app/services/combat.py, which
// resolves it). The player picks a unit, a target it can see, and the weapons
// that can reach it, and shoots - how the unit moved this turn and whether
// the target's in cover come from the battlefield.
//
// Instead of shooting, a unit can start an action one of its player's
// mission cards has (e.g. Cleanse, Plunder - see
// app/services/in_game/actions.py), where it's allowed to.
//
// With `overwatch` (GET /games/{id}/overwatch), it's Fire Overwatch instead,
// at the end of the opponent's movement phase (see
// app/services/in_game/overwatch.py): one unit snap shoots (hits only on
// unmodified 6s) at an enemy unit visible within 24", for the stratagem's CP.

function moveText(unit) {
  if (unit.advanced) return 'Advanced'
  if (unit.remained_stationary) return 'Remained stationary'
  if (unit.distance !== null) return `Moved ${unit.distance.toFixed(1)}"`
  return 'Moved'
}

function unitStatus(unit) {
  if (unit.shot) {
    const { target_name: name, total_damage: damage, models_destroyed: destroyed } = unit.shot
    return `Shot ${name}: ${damage} damage, ${destroyed} destroyed`
  }
  if (!unit.can_shoot) return `Can't shoot: ${unit.reason}`
  return moveText(unit)
}

function ShootingPanel({ game, player, shooting, overwatch, focus, onFocus, onShot, onError }) {
  const loadTargets = overwatch ? getOverwatchTargets : getShootingTargets
  const fireAt = overwatch ? fireOverwatch : shoot
  const [targets, setTargets] = useState([])
  const [weaponKeys, setWeaponKeys] = useState(new Set())
  const [outcome, setOutcome] = useState(null)
  const [busy, setBusy] = useState(false)
  // The actions each unit could start instead (not for Fire Overwatch).
  const [actions, setActions] = useState(null)
  const selected = shooting?.units.find((u) => u.unit_id === focus.unitId) ?? null
  // Only one it can see - or shoot with Indirect Fire weapons (a click on
  // the board can pick any unit).
  const target =
    targets.find((t) => t.unit_id === focus.targetId && (t.visible || t.indirect)) ?? null
  // The defending player's allocation order for the target (05.03).
  const [order, setOrder] = useState([])
  const key = (w) => `${w.firing_deck ? 'd' : w.enhancement ? 'e' : 'w'}${w.id}`

  // The selected unit's possible targets.
  useEffect(() => {
    setTargets([])
    if (!selected?.can_shoot) return
    let cancelled = false
    loadTargets(game.id, selected.unit_id)
      .then((t) => !cancelled && setTargets(t))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // Only when the unit (or whether it can still shoot) changes.
  }, [game.id, selected?.unit_id, selected?.can_shoot])

  useEffect(() => {
    if (overwatch || !shooting) {
      setActions(null)
      return
    }
    let cancelled = false
    getActions(game.id)
      .then((a) => !cancelled && setActions(a))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, shooting, overwatch])

  const act = async (unit, option, target) => {
    setBusy(true)
    onError(null)
    try {
      setActions(
        await startAction(game.id, {
          unit_id: unit.unit_id,
          action: option.action,
          target_id: target.id,
        })
      )
      onShot()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const unitActions = selected ? (actions?.options[selected.unit_id] ?? []) : []

  // Picking a target picks every weapon that can reach it.
  useEffect(() => {
    setWeaponKeys(
      new Set(onePerProfile((target?.weapons ?? []).filter((w) => w.in_range)).map(key))
    )
  }, [target])

  const fire = async () => {
    setBusy(true)
    onError(null)
    try {
      const chosen = target.weapons.filter((w) => weaponKeys.has(key(w)))
      const result = await fireAt(game.id, {
        unit_id: selected.unit_id,
        target_unit_id: target.unit_id,
        weapon_ids: chosen.filter((w) => !w.enhancement && !w.firing_deck).map((w) => w.id),
        enhancement_weapon_ids: chosen.filter((w) => w.enhancement).map((w) => w.id),
        // Its embarked models' weapons (a TRANSPORT with Firing Deck).
        firing_deck_weapon_ids: chosen.filter((w) => w.firing_deck).map((w) => w.id),
        allocation_order: order,
      })
      setOutcome({ unit: selected.name, target: target.name, ...result })
      onShot()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!shooting) return null
  // Picking one profile of a weapon unpicks its others.
  const toggleWeapon = (w) =>
    setWeaponKeys((keys) => {
      const next = new Set(keys)
      if (next.has(key(w))) next.delete(key(w))
      else {
        next.add(key(w))
        for (const other of target.weapons) {
          if (otherProfile(w.name, other.name)) next.delete(key(other))
        }
      }
      return next
    })

  return (
    <div className="deployment-panel">
      {overwatch ? (
        <>
          <h3>End of movement: Fire Overwatch</h3>
          <p>
            <strong>{player?.user_name}</strong> can use Fire Overwatch ({overwatch.cp}CP): one
            unit shoots an enemy unit it can see within 24".{' '}
            <span className="hint">
              Snap shooting: only unmodified 6s hit, with no re-rolls and no Hit roll abilities
              (Sustained or Lethal Hits). Torrent and Rapid Fire still work.
            </span>
          </p>
          {!overwatch.available && overwatch.reason && (
            <p className="hint">Can't use it: {overwatch.reason}.</p>
          )}
        </>
      ) : (
        <>
          <h3>Shooting</h3>
          <p>
            <strong>{player?.user_name}</strong> shoots.{' '}
            <span className="hint">Each unit can shoot once, at a unit it can see.</span>
          </p>
        </>
      )}
      <div className="radio-group">
        {shooting.units.map((unit) => (
          <label key={unit.unit_id} className="radio-option">
            <input
              type="radio"
              name="shoot-unit"
              checked={focus.unitId === unit.unit_id}
              onChange={() => {
                setOutcome(null)
                onFocus({ unitId: unit.unit_id, targetId: null })
              }}
            />
            {unit.name}
            {(!overwatch || unit.shot || (overwatch.available && !unit.can_shoot)) && (
              <span className="hint"> · {unitStatus(unit)}</span>
            )}
          </label>
        ))}
      </div>
      {shooting.units.length === 0 && <p className="hint">They have no units on the battlefield.</p>}

      {selected?.can_shoot && (
        <>
          <h4>Target</h4>
          <div className="radio-group">
            {targets.map((t) => (
              <label key={t.unit_id} className="radio-option">
                <input
                  type="radio"
                  name="shoot-target"
                  disabled={!t.visible && !t.indirect}
                  checked={focus.targetId === t.unit_id}
                  onChange={() => onFocus({ ...focus, targetId: t.unit_id })}
                />
                {t.name}
                <span className="hint">
                  {!t.visible &&
                    (overwatch
                      ? ' · not visible within 24"'
                      : t.indirect
                        ? ' · not visible: Indirect Fire only (hits on 6s, or 4+ if spotted)'
                        : ' · not visible')}
                  {t.visible && !t.weapons.some((w) => w.in_range) && ' · out of range'}
                  {t.in_cover && ' · in cover'}
                </span>
              </label>
            ))}
          </div>
          {targets.length === 0 && <p className="hint">No enemy units on the battlefield.</p>}
        </>
      )}

      {selected?.can_shoot && target && (
        <>
          <h4>Weapons</h4>
          <div className="radio-group">
            {target.weapons.map((w) => (
              <label key={key(w)} className="radio-option">
                <input
                  type="checkbox"
                  disabled={!w.in_range}
                  checked={weaponKeys.has(key(w))}
                  onChange={() => toggleWeapon(w)}
                />
                {w.name} ({w.range}")
                <span className="hint">
                  {w.assault ? ' · Assault' : ''}
                  {w.unusable
                    ? " · can't fire: it Advanced"
                    : ` · ${w.in_range} of ${w.carried_by} in range${w.half_range ? ' · half range' : ''}`}
                </span>
              </label>
            ))}
          </div>
          {!overwatch && (
            <p className="hint">
              {moveText(selected)}
              {selected.advanced && ' - only Assault weapons fire'}
              {!selected.advanced && selected.moved_less_than_3 && ' (moved less than 3")'}
              {target.in_cover ? ` · ${target.name} has the Benefit of Cover` : ''}
            </p>
          )}
          <AllocationOrder
            gameId={game.id}
            unitId={target.unit_id}
            defender={`${game.players.find((p) => p.seat !== player?.seat)?.user_name} (${target.name})`}
            order={order}
            onChange={setOrder}
          />
          <div className="inline-controls">
            <button type="button" disabled={busy || weaponKeys.size === 0} onClick={fire}>
              {overwatch
                ? `Fire Overwatch at ${target.name} (${overwatch.cp}CP)`
                : `Shoot ${target.name}`}
            </button>
          </div>
        </>
      )}

      {unitActions.length > 0 && (
        <>
          <h4>Or an action</h4>
          <ul className="round-start-rules">
            {unitActions.map((option) => (
              <li key={option.action}>
                <strong>{option.action}</strong>
                <span className="hint">
                  {' '}
                  · {option.card} ·{' '}
                  {option.completes === 'immediately'
                    ? 'completes straight away'
                    : 'completes at the end of the turn'}{' '}
                  · it can't shoot, charge or fight this turn
                </span>
                {option.reason ? (
                  <p className="hint">Can't: {option.reason}.</p>
                ) : (
                  <div className="inline-controls">
                    {option.targets.map((target) => (
                      <button
                        key={`${target.kind}-${target.id}`}
                        type="button"
                        disabled={busy}
                        onClick={() => act(selected, option, target)}
                      >
                        {option.action}: {target.label}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {actions?.started.length > 0 && (
        <p className="hint">
          Actions this turn:{' '}
          {actions.started
            .map((a) => `${a.unit_name} - ${a.action} (${a.target}): ${a.status}`)
            .join('; ')}
        </p>
      )}

      {outcome && (
        <div className="shooting-outcome">
          <h4>
            {outcome.unit} {overwatch ? 'fired Overwatch at' : 'shot'} {outcome.target}
          </h4>
          <CombatResults
            result={outcome.combat}
            showFnp={outcome.combat.weapon_results.some((wr) => wr.fnp_rolls.length > 0)}
          />
          {outcome.destroyed_unit_model_ids.length > 0 && (
            <p>
              <strong>
                {outcome.destroyed_unit_model_ids.length}{' '}
                {outcome.destroyed_unit_model_ids.length === 1 ? 'model' : 'models'}
              </strong>{' '}
              destroyed and removed from the battlefield (in this game only).
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default ShootingPanel
