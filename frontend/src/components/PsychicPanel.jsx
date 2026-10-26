import { useState } from 'react'
import Select from './Select'

// Psychic abilities (see app/services/in_game/psychic.py): each PSYKER unit on
// the battlefield, its psyker level and what it's used this battle round, and
// its psychic abilities - each usable when its timing allows (Soul Sight in
// its player's Shooting phase, picking a visible enemy unit; Shrouding as an
// enemy is about to attack it). Using one makes a psychic roll: on a 1, the
// unit is Battle-shocked.

function PsychicPanel({ game, psychic, onUse }) {
  const [targets, setTargets] = useState({})
  if (!psychic || psychic.units.length === 0) return null
  return (
    <div className="deployment-panel">
      <h3>Psychic abilities</h3>
      <ul className="round-start-rules">
        {psychic.units.map((unit) => (
          <li key={unit.unit_id}>
            <strong>{unit.name}</strong>
            <span className="hint">
              {' '}
              · {game.players.find((p) => p.seat === unit.seat)?.user_name}'s · psyker level{' '}
              {unit.psyker_level} ({unit.used_this_round} used this round)
            </span>
            {unit.abilities.map((ability) => {
              const key = `${unit.unit_id}-${ability.name}`
              const target = targets[key] ?? ability.targets[0]?.unit_id ?? null
              return (
                <div key={ability.name} className="command-target">
                  <span>
                    {ability.name} <span className="hint">(psychic level {ability.level})</span>
                  </span>
                  {ability.usable && ability.targets.length > 0 && (
                    <Select
                      options={ability.targets.map((t) => ({ id: String(t.unit_id), name: t.name }))}
                      value={String(target ?? '')}
                      onChange={(value) =>
                        value && setTargets((t) => ({ ...t, [key]: Number(value) }))
                      }
                    />
                  )}
                  <button
                    type="button"
                    disabled={!ability.usable}
                    title={ability.reason ?? ''}
                    onClick={() =>
                      onUse({
                        unit_id: unit.unit_id,
                        ability: ability.name,
                        target_unit_id: ability.targets.length > 0 ? target : null,
                      })
                    }
                  >
                    Use
                  </button>
                  {!ability.usable && <span className="hint"> {ability.reason}</span>}
                </div>
              )
            })}
          </li>
        ))}
      </ul>
      {psychic.uses.length > 0 && (
        <ul className="round-start-rules">
          {psychic.uses.map((use, i) => (
            <li key={i} className="hint">
              {use.unit_name}: {use.ability}
              {use.target_name ? ` on ${use.target_name}` : ''} - psychic roll {use.roll}
              {use.roll === 1 ? ' (Battle-shocked)' : ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default PsychicPanel
