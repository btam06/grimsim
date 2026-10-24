import { useEffect, useState } from 'react'
import { chooseRuleOption, getRoundStart } from '../api'
import CardTextAccordion from './CardTextAccordion'
import { RuleOptionPicker } from './RuleOptionPicker'

// The start of a battle round, before its first turn: each player's rules
// that happen then (see app/services/in_game/battle_round.py) - abilities,
// army rules, enhancements and detachment rules - as a reminder. An army rule
// with options (e.g. Doctrina Imperatives) gets the combat calculator's picker:
// the option chosen is active for that player's units this round, whenever
// they attack or are attacked. The game only stops here when a rule needs a
// decision (it has options, or its text gives a choice); the others are listed
// as reminders.

const KIND_NAMES = {
  ability: 'Ability',
  'army rule': 'Army rule',
  enhancement: 'Enhancement',
  'detachment rule': 'Detachment rule',
}

function RoundStartPanel({ game, onError }) {
  const [roundStart, setRoundStart] = useState(null)

  useEffect(() => {
    let cancelled = false
    getRoundStart(game.id)
      .then((r) => !cancelled && setRoundStart(r))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game.id, game.battle_round])

  // Picks (or clears, '') a player's option for one of their army rules.
  const choose = async (seat, abilityId, option) => {
    onError(null)
    try {
      setRoundStart(
        await chooseRuleOption(game.id, {
          seat,
          faction_ability_id: abilityId,
          option: option || null,
        })
      )
    } catch (err) {
      onError(err.message)
    }
  }

  if (!roundStart) return null
  return (
    <div className="deployment-panel">
      <h3>Start of battle round {roundStart.battle_round}</h3>
      <p className="hint">
        Before the first turn: decide what these rules need, then begin the first turn.
      </p>
      {roundStart.players.map((player) => (
        <div key={player.seat} className="round-start-player">
          <h4>{player.user_name}</h4>
          {player.rules.length === 0 && <p className="hint">Nothing at the start of this round.</p>}
          <ul className="round-start-rules">
            {player.rules.map((rule) => (
              <li key={`${rule.kind}-${rule.name}`}>
                <strong>{rule.name}</strong>
                <span className="hint">
                  {' '}
                  · {KIND_NAMES[rule.kind] ?? rule.kind}
                  {rule.units.length > 0 ? ` · ${rule.units.join(', ')}` : ''}
                </span>
                {rule.decision && <span className="round-start-decision">Decide now</span>}
                {rule.options.length > 0 && (
                  <RuleOptionPicker
                    side={player.user_name}
                    abilities={[
                      {
                        key: rule.faction_ability_id,
                        name: rule.name,
                        rule_options: rule.options,
                        option_descriptions: rule.option_descriptions,
                        required: rule.required,
                      },
                    ]}
                    choices={{ [rule.faction_ability_id]: rule.chosen ?? '' }}
                    onChange={(choices) =>
                      choose(player.seat, rule.faction_ability_id, choices[rule.faction_ability_id])
                    }
                  />
                )}
                {rule.required && !rule.chosen && (
                  <p className="hint">Choose one before the first turn.</p>
                )}
                <CardTextAccordion text={rule.description} label="Rule text" />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export default RoundStartPanel
