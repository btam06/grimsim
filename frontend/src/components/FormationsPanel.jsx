import { useEffect, useState } from 'react'
import { declareFormations, getFormations, setFormation } from '../api'
import Select from './Select'

// Declaring battle formations, at the start of deployment (see
// app/services/in_game/battle_formations.py): each player says which units
// start in Strategic Reserves (up to half their army's points) or embarked in
// one of their transports - neither is deployed - then says they're done.
// Once both have, deployment begins.

const BATTLEFIELD = 'battlefield'
const RESERVES = 'reserves'

function placeValue(unit) {
  if (unit.place === 'reserves') return RESERVES
  if (unit.place === 'embarked') return `embarked:${unit.transport_unit_id}`
  return BATTLEFIELD
}

function FormationsPanel({ game, onDeclared, onError }) {
  const [formations, setFormations] = useState(null)

  useEffect(() => {
    let cancelled = false
    getFormations(game.id)
      .then((f) => !cancelled && setFormations(f))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  const choose = async (seat, unit, value) => {
    onError(null)
    const [place, transport] = value.split(':')
    try {
      setFormations(
        await setFormation(game.id, {
          seat,
          unit_id: unit.unit_id,
          place: place === BATTLEFIELD ? null : place,
          transport_unit_id: transport ? Number(transport) : null,
        })
      )
    } catch (err) {
      onError(err.message)
    }
  }

  if (!formations) return null
  return (
    <div className="deployment-panel">
      <h3>Declare battle formations</h3>
      <p className="hint">
        Before deploying: units can start in Strategic Reserves (up to half your army&apos;s
        points) or embarked in a transport. Neither is deployed.
      </p>
      {formations.players.map((player) => {
        const transports = player.units.filter((u) => u.transport)
        return (
          <div key={player.seat} className="formation-player">
            <h4>
              {player.user_name}
              {player.done ? ' (done)' : ''}
            </h4>
            <p className="hint">
              Strategic Reserves: {player.reserves_points} of {player.reserves_limit} points
              (army {player.army_points})
            </p>
            <ul className="formation-units">
              {player.units.map((unit) => {
                const options = [
                  { id: BATTLEFIELD, name: 'Battlefield' },
                  { id: RESERVES, name: 'Strategic Reserves' },
                  ...(unit.transport
                    ? []
                    : transports.map((t) => ({
                        id: `embarked:${t.unit_id}`,
                        name: `Embarked in ${t.name}`,
                      }))),
                ]
                return (
                  <li key={unit.unit_id}>
                    <span>
                      {unit.name} <span className="hint">· {unit.points} pts</span>
                    </span>
                    <Select
                      options={options}
                      value={placeValue(unit)}
                      onChange={(value) => value && choose(player.seat, unit, value)}
                      isDisabled={player.done}
                    />
                  </li>
                )
              })}
            </ul>
            <div className="inline-controls">
              <button
                type="button"
                disabled={player.done}
                onClick={() => onDeclared(player.seat)}
              >
                {player.done ? 'Declared' : `Done - ${player.user_name}'s formations`}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default FormationsPanel
