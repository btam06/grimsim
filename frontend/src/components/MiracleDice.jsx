import { useEffect, useState } from 'react'
import { getMiracleDice } from '../api'

// Acts of Faith (an ADEPTA SORORITAS army - see
// app/seeds/factions/adepta_sororitas/acts_of_faith.py): a unit with the
// ability can perform one Act of Faith a phase, using a Miracle dice from its
// player's pool in place of one die of a roll (an unmodified roll of that
// value). These are offered only while the unit can - it has the ability,
// hasn't performed one this phase, and there's a dice in the pool.

const ROLL_NAMES = {
  advance: 'Advance roll',
  battle_shock: 'Battle-shock test',
  charge: 'Charge roll',
  damage: 'Damage roll',
  hit: 'Hit roll',
  save: 'Saving throw',
  wound: 'Wound roll',
}

// The player whose unit it is, if it can perform an Act of Faith now.
export function actOfFaithPlayer(game, unitId) {
  return (
    game?.players.find(
      (p) => p.miracle_dice?.length > 0 && p.act_of_faith_unit_ids?.includes(unitId)
    ) ?? null
  )
}

// The pool's distinct values, highest first.
function values(player) {
  return [...new Set(player.miracle_dice)].sort((a, b) => b - a)
}

// A player's Miracle dice pool, e.g. for the scoreboard.
export function MiracleDicePool({ player }) {
  if (!player?.acts_of_faith) return null
  const pool = [...(player.miracle_dice ?? [])].sort((a, b) => b - a)
  return (
    <span className="miracle-pool" title="Miracle dice (Acts of Faith)">
      Miracle dice: {pool.length ? pool.join(', ') : 'none'}
    </span>
  )
}

// For a single roll (Advance, charge, Battle-shock): roll as normal, or use
// a Miracle dice of the chosen value for one of its dice. `value` is that
// value, or null.
export function MiracleDiePicker({ game, unitId, roll, value, onChange }) {
  const player = actOfFaithPlayer(game, unitId)
  if (!player) return null
  return (
    <label className="miracle-picker">
      Act of Faith ({ROLL_NAMES[roll]}):{' '}
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      >
        <option value="">No - roll</option>
        {values(player).map((v) => (
          <option key={v} value={v}>
            Miracle dice {v}
          </option>
        ))}
      </select>
    </label>
  )
}

// For an attack: the unit's Act of Faith, for one of `rolls` (e.g. Hit,
// Wound, Damage for the attacker; a Saving throw for the defender) - the
// first such roll in the attack, optionally with one of `weapons` ({id,
// name}). `value` is {roll, value, weapon_id} (MiracleIn) or null.
export function AttackMiraclePicker({ game, unitId, who, rolls, weapons = [], value, onChange }) {
  const player = actOfFaithPlayer(game, unitId)
  if (!player) return null
  const pool = values(player)
  const current = value ?? { roll: rolls[0], value: null, weapon_id: null }
  const set = (change) => {
    const next = { ...current, ...change }
    onChange(next.value === null ? null : next)
  }
  return (
    <div className="miracle-picker">
      <span>
        {who}: Act of Faith{' '}
        <span className="hint">
          (a Miracle dice for the first such roll - an unmodified roll of its value)
        </span>
      </span>
      <div className="inline-controls">
        <select
          value={current.value ?? ''}
          onChange={(e) => set({ value: e.target.value === '' ? null : Number(e.target.value) })}
        >
          <option value="">None</option>
          {pool.map((v) => (
            <option key={v} value={v}>
              Miracle dice {v}
            </option>
          ))}
        </select>
        {rolls.length > 1 && (
          <select value={current.roll} onChange={(e) => set({ roll: e.target.value })}>
            {rolls.map((r) => (
              <option key={r} value={r}>
                {ROLL_NAMES[r]}
              </option>
            ))}
          </select>
        )}
        {rolls.length === 1 && <span>{ROLL_NAMES[rolls[0]]}</span>}
        {weapons.length > 1 && (
          <select
            value={current.weapon_id ?? ''}
            onChange={(e) =>
              set({ weapon_id: e.target.value === '' ? null : Number(e.target.value) })
            }
          >
            <option value="">Any weapon</option>
            {weapons.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  )
}

export const ATTACK_ROLLS = ['hit', 'wound', 'damage']
export const DEFENCE_ROLLS = ['save']

// Abilities that discard a Miracle dice as the unit's selected to shoot or
// fight (e.g. Righteous Repugnance, Rapturous Blows - see
// GET /games/{id}/miracle-dice selection_discards). `value` is {ability name:
// the dice's value}.
export function SelectionDiscards({ game, unitId, value, onChange, onError }) {
  const [options, setOptions] = useState({ names: [], pool: [] })
  useEffect(() => {
    setOptions({ names: [], pool: [] })
    if (unitId == null) return
    let cancelled = false
    getMiracleDice(game.id)
      .then((players) => {
        if (cancelled) return
        const owner = players.find((p) => p.selection_discards[unitId])
        if (owner) setOptions({ names: owner.selection_discards[unitId], pool: owner.pool })
      })
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, unitId])
  if (options.names.length === 0) return null
  const values = [...new Set(options.pool)].sort((a, b) => a - b)
  return (
    <div className="miracle-picker">
      {options.names.map((name) => (
        <label key={name} className="miracle-picker">
          {name}: discard a Miracle dice{' '}
          <select
            value={value[name] ?? ''}
            onChange={(e) => {
              const next = { ...value }
              if (e.target.value === '') delete next[name]
              else next[name] = Number(e.target.value)
              onChange(next)
            }}
          >
            <option value="">No</option>
            {values.map((v) => (
              <option key={v} value={v}>
                Discard {v}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  )
}
