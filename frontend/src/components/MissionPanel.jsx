import { useState } from 'react'
import { answerMissionPrompt } from '../api'
import Select from './Select'

// Missions' choices (see app/services/in_game/mission_state.py): placing
// operation markers (Locate and Deny), consecrating objectives (Consecrate),
// condemning enemy units (Punishment), removing a marker after a sensor
// sweep, and secondary cards' choices when drawn (Beacon's unit, Burden of
// Trust's guards, A Tempting Target's objective - picked by the opponent) -
// the game waits until each is made - and the units missions have marked
// (condemned, surveilled, consecration units).

const MARK_NAMES = {
  condemned: 'Condemned',
  surveilled: 'Surveilled',
  consecration: 'Consecration unit',
}

function Prompt({ game, prompt, onAnswered, onError }) {
  const [picked, setPicked] = useState([])
  // Consecration: {unit id: objective id}.
  const [consecrations, setConsecrations] = useState({})
  // Guards: {objective id: unit id}.
  const [guards, setGuards] = useState({})
  const [busy, setBusy] = useState(false)
  const player = game.players.find((p) => p.seat === prompt.seat)

  const submit = async () => {
    setBusy(true)
    onError(null)
    try {
      onAnswered(
        await answerMissionPrompt(game.id, prompt.id, {
          ids: picked,
          consecrations,
          guards,
        })
      )
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const toggle = (id) =>
    setPicked((current) => {
      if (prompt.pick_max === 1) return [id]
      return current.includes(id) ? current.filter((i) => i !== id) : [...current, id]
    })

  if (prompt.kind === 'consecrate') {
    const units = [...new Set(prompt.options.map((o) => o.unit_id))]
    return (
      <li>
        <strong>{player?.user_name}</strong> · {prompt.mission}
        <p className="hint">{prompt.text}</p>
        {units.map((unitId) => {
          const options = prompt.options.filter((o) => o.unit_id === unitId)
          return (
            <div key={unitId} className="radio-group">
              {[{ id: null, label: "Don't consecrate" }, ...options].map((o) => (
                <label key={o.id ?? 'none'} className="radio-option">
                  <input
                    type="radio"
                    name={`consecrate-${prompt.id}-${unitId}`}
                    checked={(consecrations[unitId] ?? null) === o.id}
                    onChange={() =>
                      setConsecrations((c) => {
                        const next = { ...c }
                        if (o.id === null) delete next[unitId]
                        else next[unitId] = o.id
                        return next
                      })
                    }
                  />
                  {o.label}
                </label>
              ))}
            </div>
          )
        })}
        <div className="inline-controls">
          <button type="button" disabled={busy} onClick={submit}>
            Done
          </button>
        </div>
      </li>
    )
  }

  if (prompt.kind === 'guards') {
    return (
      <li>
        <strong>{player?.user_name}</strong> · {prompt.mission}
        <p className="hint">{prompt.text}</p>
        {prompt.options.map((objective) => (
          <div key={objective.id} className="command-target">
            <span className="hint">{objective.label}:</span>
            <Select
              options={[
                { id: '', name: 'Not guarded' },
                ...prompt.units.map((u) => ({ id: u.id, name: u.label })),
              ]}
              value={guards[objective.id] ? String(guards[objective.id]) : ''}
              onChange={(value) =>
                setGuards((g) => {
                  const next = { ...g }
                  if (value) next[objective.id] = Number(value)
                  else delete next[objective.id]
                  return next
                })
              }
            />
          </div>
        ))}
        <div className="inline-controls">
          <button type="button" disabled={busy} onClick={submit}>
            Done
          </button>
        </div>
      </li>
    )
  }

  const ready = picked.length >= prompt.pick_min && picked.length <= prompt.pick_max
  return (
    <li>
      <strong>{player?.user_name}</strong> · {prompt.mission}
      <p className="hint">{prompt.text}</p>
      <div className="radio-group">
        {prompt.options.map((o) => (
          <label key={o.id} className="radio-option">
            <input
              type={prompt.pick_max === 1 ? 'radio' : 'checkbox'}
              name={`prompt-${prompt.id}`}
              checked={picked.includes(o.id)}
              onChange={() => toggle(o.id)}
            />
            {o.label}
          </label>
        ))}
      </div>
      <div className="inline-controls">
        <button type="button" disabled={busy || !ready} onClick={submit}>
          {prompt.pick_min === prompt.pick_max
            ? `Confirm (${picked.length}/${prompt.pick_max})`
            : `Confirm (${picked.length} picked)`}
        </button>
      </div>
    </li>
  )
}

function MissionPanel({ game, mission, onAnswered, onError }) {
  if (!mission || (mission.prompts.length === 0 && mission.marked.length === 0)) return null
  const nameOf = (seat) => game.players.find((p) => p.seat === seat)?.user_name
  return (
    <div className="deployment-panel">
      <h3>Missions</h3>
      {mission.prompts.length > 0 && (
        <ul className="round-start-rules">
          {mission.prompts.map((prompt) => (
            <Prompt
              key={prompt.id}
              game={game}
              prompt={prompt}
              onAnswered={onAnswered}
              onError={onError}
            />
          ))}
        </ul>
      )}
      {mission.marked.length > 0 && (
        <p className="hint">
          {mission.marked
            .map(
              (m) =>
                `${MARK_NAMES[m.kind] ?? m.kind}: ${m.unit_name} (${nameOf(m.seat)}'s mission)`
            )
            .join(' · ')}
        </p>
      )}
    </div>
  )
}

export default MissionPanel
