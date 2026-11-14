import { useEffect, useState } from 'react'
import {
  getFormations,
  grantFormationAbility,
  setFormation,
  splitUnit,
  unsplitUnit,
} from '../api'
import Select from './Select'

// Declaring battle formations, at the start of deployment (see
// app/services/in_game/battle_formations.py): each player says which units
// start in Strategic Reserves (up to half their army's points) or embarked in
// one of their transports - neither is deployed - then says they're done.
// Once both have, deployment begins. A transport that splits a unit (e.g. an
// Immolator - see app/services/in_game/unit_splits.py) does so first: one
// half must then start embarked in it.

const BATTLEFIELD = 'battlefield'
const RESERVES = 'reserves'

function placeValue(unit) {
  if (unit.place === 'reserves') return RESERVES
  if (unit.place === 'embarked') return `embarked:${unit.transport_unit_id}`
  return BATTLEFIELD
}

function FormationsPanel({ game, onDeclared, onChanged, onError }) {
  const [formations, setFormations] = useState(null)
  // Which half of a unit being split keeps its Cherub, by transport.
  const [cherubNew, setCherubNew] = useState({})
  // The unit picked to split, and the models picked to go in the transport,
  // by transport.
  const [splitUnitId, setSplitUnitId] = useState({})
  const [picked, setPicked] = useState({})

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

  const split = async (seat, transportId, unitId, modelIds) => {
    onError(null)
    try {
      setFormations(
        await splitUnit(game.id, {
          seat,
          transport_unit_id: transportId,
          unit_id: unitId,
          cherub_to_new: Boolean(cherubNew[transportId]),
          unit_model_ids: modelIds,
          embark: true,
        })
      )
      setSplitUnitId((c) => ({ ...c, [transportId]: null }))
      setPicked((c) => ({ ...c, [transportId]: [] }))
      onChanged?.()
    } catch (err) {
      onError(err.message)
    }
  }
  const unsplit = async (seat, unitId) => {
    onError(null)
    try {
      setFormations(await unsplitUnit(game.id, { seat, unit_id: unitId }))
      onChanged?.()
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
            {(player.splits ?? []).map((sp) => {
              const name = (id) => player.units.find((u) => u.unit_id === id)?.name ?? `#${id}`
              return (
                <div key={sp.transport_unit_id} className="formation-grant">
                  {sp.unit_id == null ? (
                    sp.candidates.length > 0 && (
                      <>
                        <span>
                          {sp.transport_name} can split a squad in two (one half starts embarked
                          in it):
                        </span>
                        <Select
                          options={sp.candidates.map((c) => ({ id: c.unit_id, name: c.name }))}
                          value={
                            splitUnitId[sp.transport_unit_id] == null
                              ? ''
                              : String(splitUnitId[sp.transport_unit_id])
                          }
                          onChange={(value) => {
                            setSplitUnitId((c) => ({
                              ...c,
                              [sp.transport_unit_id]: value ? Number(value) : null,
                            }))
                            setPicked((c) => ({ ...c, [sp.transport_unit_id]: [] }))
                          }}
                          isDisabled={player.done}
                        />
                        {(() => {
                          const candidate = sp.candidates.find(
                            (c) => c.unit_id === splitUnitId[sp.transport_unit_id]
                          )
                          if (!candidate) return null
                          const chosen = picked[sp.transport_unit_id] ?? []
                          const toggle = (id) =>
                            setPicked((c) => {
                              const current = c[sp.transport_unit_id] ?? []
                              return {
                                ...c,
                                [sp.transport_unit_id]: current.includes(id)
                                  ? current.filter((x) => x !== id)
                                  : [...current, id],
                              }
                            })
                          return (
                            <div>
                              <p className="hint">
                                Pick the models going in {sp.transport_name} (
                                {candidate.sizes.join(' or ')} - {chosen.length} picked):
                              </p>
                              {candidate.models.map((m, n) => (
                                <label key={m.unit_model_id} className="radio-option">
                                  <input
                                    type="checkbox"
                                    checked={chosen.includes(m.unit_model_id)}
                                    disabled={player.done}
                                    onChange={() => toggle(m.unit_model_id)}
                                  />
                                  {n + 1}. {m.name}
                                  {m.weapons.length > 0 && (
                                    <span className="hint"> · {m.weapons.join(', ')}</span>
                                  )}
                                </label>
                              ))}
                              <button
                                type="button"
                                disabled={player.done || !candidate.sizes.includes(chosen.length)}
                                onClick={() =>
                                  split(
                                    player.seat,
                                    sp.transport_unit_id,
                                    candidate.unit_id,
                                    chosen
                                  )
                                }
                              >
                                Split: {chosen.length} into {sp.transport_name}
                              </button>
                            </div>
                          )
                        })()}
                        <label className="radio-option">
                          <input
                            type="checkbox"
                            checked={Boolean(cherubNew[sp.transport_unit_id])}
                            disabled={player.done}
                            onChange={(e) =>
                              setCherubNew((c) => ({ ...c, [sp.transport_unit_id]: e.target.checked }))
                            }
                          />
                          The half in {sp.transport_name} keeps the Cherub
                        </label>
                      </>
                    )
                  ) : (
                    <>
                      <span>
                        {sp.transport_name} split {name(sp.unit_id)} and {name(sp.new_unit_id)}
                        {sp.cherub_unit_id != null && ` (Cherub: ${name(sp.cherub_unit_id)})`} -
                        one must start embarked in it.
                      </span>
                      {!player.done && (
                        <button type="button" onClick={() => unsplit(player.seat, sp.unit_id)}>
                          Undo split
                        </button>
                      )}
                    </>
                  )}
                </div>
              )
            })}
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
            {(player.grants ?? []).map((grant) => (
              // Abilities that give another unit an ability now (e.g.
              // Thunderhawk Insertion: Deep Strike).
              <div key={`${grant.source_unit_id}-${grant.ability}`} className="formation-grant">
                <span>
                  {grant.ability} <span className="hint">({grant.source_name})</span>:{' '}
                  {grant.grants} for
                </span>
                <Select
                  options={[
                    { id: 'none', name: 'No unit' },
                    ...grant.targets.map((t) => ({ id: t.unit_id, name: t.name })),
                  ]}
                  value={grant.unit_id == null ? 'none' : String(grant.unit_id)}
                  onChange={(value) =>
                    grantFormationAbility(game.id, {
                      seat: player.seat,
                      source_unit_id: grant.source_unit_id,
                      ability: grant.ability,
                      unit_id: value && value !== 'none' ? Number(value) : null,
                    })
                      .then(setFormations)
                      .catch((err) => onError(err.message))
                  }
                  isDisabled={player.done}
                />
              </div>
            ))}
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
