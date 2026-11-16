import { useEffect, useState } from 'react'
import { getActivations, getReactiveShots, takeReactiveShot, activateAbility } from '../api'
import ActivationButtons from './ActivationButtons'

// Abilities a player chooses to use (see app/services/in_game/activations.py):
// once a battle, round, turn or phase, in their window - e.g. Lord of the
// Storm, Gravitic Pulse, the Silent King's Triarch Abilities - each with what
// it can target now (or why it can't be used). Those used at the start or end
// of a phase are offered in that step's panel (PhaseStepPanel) instead. And
// shots units can take in their opponent's turn (app/services/in_game/reactive_shots.py - e.g.
// Hyperspace Hunters at a unit that arrived from Reserves), with every
// weapon that can reach the target. Shown while any unit has one.

function AbilitiesPanel({ game, onChange, onError }) {
  const [activations, setActivations] = useState([])
  const [shots, setShots] = useState([])
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([getActivations(game.id), getReactiveShots(game.id)])
      .then(([a, s]) => {
        if (cancelled) return
        // (Those for the start or end of a phase are in its step's panel.)
        setActivations(a.filter((x) => x.when !== 'start' && x.when !== 'end'))
        setShots(s)
      })
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game])

  if (activations.length === 0 && shots.length === 0) return null

  const run = async (action) => {
    setBusy(true)
    onError(null)
    try {
      await action()
      onChange()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const activate = (a, payload) =>
    run(async () => {
      const result = await activateAbility(game.id, {
        unit_id: a.unit_id,
        ability: a.ability,
        ...payload,
      })
      setNote(`${a.ability}: ${result.note}`)
      setActivations(result.activations.filter((x) => x.when !== 'start' && x.when !== 'end'))
    })

  const shoot = (s, target) =>
    run(async () => {
      const result = await takeReactiveShot(game.id, {
        unit_id: s.unit_id,
        target_unit_id: target.unit_id,
        ability: s.ability,
        weapon_ids: [],
      })
      if (result.combat) setNote(`${s.ability}: ${result.combat.total_damage} damage to ${target.name}`)
    })

  return (
    <div className="deployment-panel">
      <h3>Abilities</h3>
      {note && <p className="hint">{note}</p>}
      {activations.map((a) => (
        <div key={`${a.unit_id}:${a.ability}`}>
          <p>
            {a.name} ({a.ability}){' '}
            <span className="hint">{a.reason ? `- ${a.reason}` : `- ${a.description}`}</span>
          </p>
          {!a.reason && <ActivationButtons activation={a} busy={busy} onActivate={activate} />}
        </div>
      ))}
      {shots.map((s) => (
        <div key={`${s.unit_id}:${s.ability}`}>
          <p>
            {s.name} ({s.ability}){' '}
            <span className="hint">- can shoot, as if it were its Shooting phase</span>
          </p>
          <div className="inline-controls">
            {s.targets.map((t) => (
              <button key={t.unit_id} type="button" disabled={busy} onClick={() => shoot(s, t)}>
                Shoot {t.name}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default AbilitiesPanel
