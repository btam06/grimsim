import { useEffect, useState } from 'react'
import {
  discardForManual,
  getMiracleDice,
  rerollWithChaplet,
  resolvePsalm,
  sacredHealing,
} from '../api'

// The Adepta Sororitas rules that discard or re-roll Miracle dice, offered
// when they can be used (see app/seeds/factions/adepta_sororitas/miracle_rules.py
// - GET /games/{id}/miracle-dice):
//
// - Manual of Saint Griselda: the start of its player's Command phase - discard
//   up to 2, gain one showing their sum (at most 6).
// - Chaplet of Sacrifice: the end of its player's Command phase - re-roll 1
//   (3 if its bearer's unit is below Starting Strength).
// - Psalm of Righteous Judgement: a PENITENT unit just destroyed an enemy unit
//   - discard 1 for a 6, or decline.
//
// (Righteous Rage is picked as a unit fights - see FightPanel.)

// Picks dice from the pool: `picked` is a list of indexes into it.
function DicePicker({ pool, max, picked, onChange }) {
  return (
    <div className="inline-controls">
      {pool.map((value, i) => {
        const on = picked.includes(i)
        return (
          <label key={i} className="radio-option">
            <input
              type="checkbox"
              checked={on}
              disabled={!on && picked.length >= max}
              onChange={() => onChange(on ? picked.filter((p) => p !== i) : [...picked, i])}
            />
            {value}
          </label>
        )
      })}
    </div>
  )
}

function PlayerMiracles({ game, state, onDone, onError }) {
  const [manual, setManual] = useState([])
  const [chaplet, setChaplet] = useState([])
  const [busy, setBusy] = useState(false)
  const name = game.players.find((p) => p.seat === state.seat)?.user_name
  const values = (picked) => picked.map((i) => state.pool[i])

  const run = async (action) => {
    setBusy(true)
    onError(null)
    try {
      onDone(await action())
      setManual([])
      setChaplet([])
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p>
        <strong>{name}</strong> · Miracle dice: {state.pool.length ? state.pool.join(', ') : 'none'}
      </p>
      {state.manual && (
        <div>
          <span>
            Manual of Saint Griselda{' '}
            <span className="hint">
              (start of the Command phase): discard up to 2, gain one showing their sum (max 6)
            </span>
          </span>
          <DicePicker pool={state.pool} max={2} picked={manual} onChange={setManual} />
          <button
            type="button"
            disabled={busy || manual.length === 0}
            onClick={() =>
              run(() => discardForManual(game.id, { seat: state.seat, values: values(manual) }))
            }
          >
            Discard {values(manual).join(' + ') || '...'} for a{' '}
            {Math.min(6, values(manual).reduce((a, b) => a + b, 0)) || '?'}
          </button>
        </div>
      )}
      {!state.manual && state.manual_reason && (
        <p className="hint">Manual of Saint Griselda: {state.manual_reason}.</p>
      )}
      {state.chaplet > 0 && (
        <div>
          <span>
            Chaplet of Sacrifice{' '}
            <span className="hint">
              (end of the Command phase - no Miracle dice can be used after it this phase):
              re-roll up to {state.chaplet}
            </span>
          </span>
          <DicePicker
            pool={state.pool}
            max={state.chaplet}
            picked={chaplet}
            onChange={setChaplet}
          />
          <button
            type="button"
            disabled={busy || chaplet.length === 0}
            onClick={() =>
              run(() => rerollWithChaplet(game.id, { seat: state.seat, values: values(chaplet) }))
            }
          >
            Re-roll {values(chaplet).join(', ') || '...'}
          </button>
        </div>
      )}
      {state.chaplet === 0 && state.chaplet_reason && (
        <p className="hint">Chaplet of Sacrifice: {state.chaplet_reason}.</p>
      )}
      {state.offers.map((offer) => (
        <div key={offer.id}>
          <span>
            {offer.rule}{' '}
            <span className="hint">
              ({offer.unit_name} destroyed): discard a Miracle dice to gain a 6?
            </span>
          </span>
          <div className="inline-controls">
            {[...new Set(state.pool)].map((value) => (
              <button
                key={value}
                type="button"
                disabled={busy || value === 6}
                onClick={() =>
                  run(() =>
                    resolvePsalm(game.id, { seat: state.seat, offer_id: offer.id, value })
                  )
                }
              >
                Discard {value}
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  resolvePsalm(game.id, { seat: state.seat, offer_id: offer.id, value: null })
                )
              }
            >
              Decline
            </button>
          </div>
        </div>
      ))}
      {state.sacred_healing.map((healing) => (
        <div key={healing.unit_id}>
          <span>
            Sacred Healing{' '}
            <span className="hint">
              ({healing.name}, {healing.destroyed} destroyed): return 1 model - or discard a
              Miracle dice to return up to D3+1
            </span>
          </span>
          <div className="inline-controls">
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => sacredHealing(game.id, { unit_id: healing.unit_id }))}
            >
              Return 1
            </button>
            {[...new Set(state.pool)].map((value) => (
              <button
                key={value}
                type="button"
                disabled={busy}
                onClick={() =>
                  run(() => sacredHealing(game.id, { unit_id: healing.unit_id, discard: value }))
                }
              >
                Discard {value}: return up to D3+1
              </button>
            ))}
          </div>
        </div>
      ))}
      {state.used.map((use, i) => (
        <p key={i} className="hint">
          {use.rule}: {use.removed.length ? `discarded ${use.removed.join(', ')}` : ''}
          {use.added.length ? `${use.removed.length ? '; ' : ''}now ${use.added.join(', ')}` : ''}
        </p>
      ))}
    </div>
  )
}

function MiracleDicePanel({ game, onChange, onError }) {
  const [players, setPlayers] = useState([])

  // Again whenever the game changes (a phase, a unit destroyed, a dice used).
  useEffect(() => {
    let cancelled = false
    getMiracleDice(game.id)
      .then((p) => !cancelled && setPlayers(p))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  // Only while one of them has something to use (or has used one this phase).
  const shown = players.filter(
    (p) =>
      p.manual ||
      p.chaplet > 0 ||
      p.offers.length > 0 ||
      p.used.length > 0 ||
      (p.sacred_healing ?? []).length > 0
  )
  if (shown.length === 0) return null
  return (
    <div className="deployment-panel">
      <h3>Miracle dice</h3>
      {shown.map((state) => (
        <PlayerMiracles
          key={state.seat}
          game={game}
          state={state}
          onDone={(p) => {
            setPlayers(p)
            onChange()
          }}
          onError={onError}
        />
      ))}
    </div>
  )
}

export default MiracleDicePanel
