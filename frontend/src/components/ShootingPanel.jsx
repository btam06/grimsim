import { useEffect, useState } from 'react'
import { getShootingTargets, shoot } from '../api'
import CombatResults from './CombatResults'

// Shooting in the shooting phase (see app/services/in_game/shooting.py, which decides
// what each unit can see and reach, and app/services/combat.py, which
// resolves it). The player picks a unit, a target it can see, and the weapons
// that can reach it, and shoots - how the unit moved this turn and whether
// the target's in cover come from the battlefield.

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

function ShootingPanel({ game, player, shooting, focus, onFocus, onShot, onError }) {
  const [targets, setTargets] = useState([])
  const [weaponKeys, setWeaponKeys] = useState(new Set())
  const [outcome, setOutcome] = useState(null)
  const [busy, setBusy] = useState(false)
  const selected = shooting?.units.find((u) => u.unit_id === focus.unitId) ?? null
  const target = targets.find((t) => t.unit_id === focus.targetId) ?? null
  const key = (w) => `${w.enhancement ? 'e' : 'w'}${w.id}`

  // The selected unit's possible targets.
  useEffect(() => {
    setTargets([])
    if (!selected?.can_shoot) return
    let cancelled = false
    getShootingTargets(game.id, selected.unit_id)
      .then((t) => !cancelled && setTargets(t))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // Only when the unit (or whether it can still shoot) changes.
  }, [game.id, selected?.unit_id, selected?.can_shoot])

  // Picking a target picks every weapon that can reach it.
  useEffect(() => {
    setWeaponKeys(new Set((target?.weapons ?? []).filter((w) => w.in_range).map(key)))
  }, [target])

  const fire = async () => {
    setBusy(true)
    onError(null)
    try {
      const chosen = target.weapons.filter((w) => weaponKeys.has(key(w)))
      const result = await shoot(game.id, {
        unit_id: selected.unit_id,
        target_unit_id: target.unit_id,
        weapon_ids: chosen.filter((w) => !w.enhancement).map((w) => w.id),
        enhancement_weapon_ids: chosen.filter((w) => w.enhancement).map((w) => w.id),
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
  const toggleWeapon = (w) =>
    setWeaponKeys((keys) => {
      const next = new Set(keys)
      if (next.has(key(w))) next.delete(key(w))
      else next.add(key(w))
      return next
    })

  return (
    <div className="deployment-panel">
      <h3>Shooting</h3>
      <p>
        <strong>{player?.user_name}</strong> shoots.{' '}
        <span className="hint">Each unit can shoot once, at a unit it can see.</span>
      </p>
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
            <span className="hint"> · {unitStatus(unit)}</span>
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
                  disabled={!t.visible}
                  checked={focus.targetId === t.unit_id}
                  onChange={() => onFocus({ ...focus, targetId: t.unit_id })}
                />
                {t.name}
                <span className="hint">
                  {!t.visible && ' · not visible'}
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
          <p className="hint">
            {moveText(selected)}
            {selected.advanced && ' - only Assault weapons fire'}
            {!selected.advanced && selected.moved_less_than_3 && ' (moved less than 3")'}
            {target.in_cover ? ` · ${target.name} has the Benefit of Cover` : ''}
          </p>
          <div className="inline-controls">
            <button type="button" disabled={busy || weaponKeys.size === 0} onClick={fire}>
              Shoot {target.name}
            </button>
          </div>
        </>
      )}

      {outcome && (
        <div className="shooting-outcome">
          <h4>
            {outcome.unit} shot {outcome.target}
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
