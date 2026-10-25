import { useEffect, useState } from 'react'
import { chooseCommandOption, getCommand } from '../api'
import CardTextAccordion from './CardTextAccordion'
import { RuleOptionPicker } from './RuleOptionPicker'
import Select from './Select'

// The Command phase's abilities (see app/services/in_game/command_phase.py):
// the player whose turn it is selects an option for each of their units'
// abilities that have one then (e.g. Canticles of the Omnissiah, Rod of the
// War Forge, Battle Protocols) - with the combat calculator's picker - and,
// for one that applies to another unit, which unit; for an option against
// one enemy unit (Invocation of Machine Vengeance), which enemy unit. Most must be selected
// before the phase ends and last until their next Command phase; Battle
// Protocols stay until changed. Models that healed at the start of the phase
// (e.g. Self-repair Mechanisms) are listed too.

function abilityKey(ability) {
  return `${ability.unit_id}-${ability.ability}`
}

function CommandPanel({ game, onError }) {
  const [command, setCommand] = useState(null)
  // The unit picked for each ability that applies to another unit, before
  // an option is.
  const [targets, setTargets] = useState({})

  useEffect(() => {
    let cancelled = false
    getCommand(game.id)
      .then((c) => !cancelled && setCommand(c))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, game.battle_round, game.turn_seat, game.phase])

  const targetOf = (ability) =>
    targets[abilityKey(ability)] ?? ability.target_unit_id ?? ability.targets[0]?.unit_id ?? null

  // The enemy unit for an option that targets one: picked, or its current
  // target, or the first there is.
  const enemyTargetOf = (ability, option) => {
    const enemies = ability.option_targets?.[option] ?? []
    const picked = targets[`${abilityKey(ability)}-${option}`]
    const current = ability.active === option ? ability.target_unit_id : null
    return picked ?? current ?? enemies[0]?.unit_id ?? null
  }

  const targetFor = (ability, option) => {
    if (!option) return null
    if (ability.option_targets?.[option]) return enemyTargetOf(ability, option)
    return ability.needs_target ? targetOf(ability) : null
  }

  const choose = async (ability, option, target = targetFor(ability, option)) => {
    onError(null)
    try {
      setCommand(
        await chooseCommandOption(game.id, {
          seat: command.seat,
          unit_id: ability.unit_id,
          ability: ability.ability,
          option: option || null,
          target_unit_id: option ? target : null,
        })
      )
    } catch (err) {
      onError(err.message)
    }
  }

  if (!command || command.seat === null) return null
  if (command.abilities.length === 0 && command.heals.length === 0) return null
  const player = game.players.find((p) => p.seat === command.seat)

  return (
    <div className="deployment-panel">
      <h3>Command phase</h3>
      <p>
        <strong>{player?.user_name}</strong>&apos;s abilities this Command phase.
      </p>
      {command.heals.length > 0 && (
        <ul className="round-start-rules">
          {command.heals.map((heal, i) => (
            <li key={i}>
              <strong>{heal.ability}</strong>
              <span className="hint">
                {' '}
                · {heal.unit_name}: rolled {heal.roll},{' '}
                {heal.healed === 0
                  ? 'no wounds to regain'
                  : `regained ${heal.healed} ${heal.healed === 1 ? 'wound' : 'wounds'}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <ul className="round-start-rules">
        {command.abilities.map((ability) => {
          const key = abilityKey(ability)
          const noTargets = ability.needs_target && ability.targets.length === 0
          return (
            <li key={key}>
              <strong>{ability.ability}</strong>
              <span className="hint"> · {ability.unit_name}</span>
              {ability.required && !ability.chosen && !noTargets && (
                <span className="round-start-decision">Decide now</span>
              )}
              {ability.needs_target && (
                <div className="command-target">
                  <span className="hint">Unit:</span>
                  <Select
                    options={ability.targets.map((t) => ({ id: t.unit_id, name: t.name }))}
                    value={targetOf(ability) === null ? '' : String(targetOf(ability))}
                    placeholder={noTargets ? 'No unit in range' : 'Choose a unit'}
                    isDisabled={noTargets}
                    onChange={(value) => {
                      const target = value ? Number(value) : null
                      setTargets((t) => ({ ...t, [key]: target }))
                      // Already selected this phase: move it to that unit.
                      if (ability.chosen && ability.active && target !== null) {
                        choose(ability, ability.active, target)
                      }
                    }}
                  />
                </div>
              )}
              {!noTargets && (
                <RuleOptionPicker
                  side={ability.unit_name}
                  abilities={[
                    {
                      key,
                      name: ability.ability,
                      rule_options: ability.options,
                      option_descriptions: ability.option_descriptions,
                      // A persistent one always has one active.
                      required: ability.required || ability.persistent,
                    },
                  ]}
                  choices={{ [key]: ability.chosen || ability.persistent ? ability.active : '' }}
                  onChange={(choices) => choose(ability, choices[key])}
                />
              )}
              {ability.active && ability.option_targets?.[ability.active] && (
                <div className="command-target">
                  <span className="hint">{ability.active} target:</span>
                  <Select
                    options={ability.option_targets[ability.active].map((t) => ({
                      id: t.unit_id,
                      name: t.name,
                    }))}
                    value={String(enemyTargetOf(ability, ability.active) ?? '')}
                    placeholder="Choose an enemy unit"
                    onChange={(value) => {
                      if (!value) return
                      const target = Number(value)
                      setTargets((t) => ({ ...t, [`${key}-${ability.active}`]: target }))
                      choose(ability, ability.active, target)
                    }}
                  />
                </div>
              )}
              {noTargets && (
                <p className="hint">No unit it could apply to is in range: nothing to select.</p>
              )}
              {ability.persistent && !ability.chosen && (
                <p className="hint">Stays in {ability.active} unless you change it.</p>
              )}
              {ability.required && !ability.chosen && !noTargets && (
                <p className="hint">Select one before the Command phase ends.</p>
              )}
              <CardTextAccordion text={ability.description} label="Rule text" />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default CommandPanel
