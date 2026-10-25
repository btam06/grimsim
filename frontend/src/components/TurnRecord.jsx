import { useEffect, useState } from 'react'
import { getTurnRecord } from '../api'
import CardTextAccordion from './CardTextAccordion'

// What has happened this turn, for missions (see
// app/services/in_game/turn_record.py): the units and models destroyed (and
// by whom), and who controlled each objective - and who was on it - at the
// start of the turn. Collapsed until opened.

const KIND_NAMES = {
  attacker_home: "attacker's home",
  defender_home: "defender's home",
  expansion: 'expansion',
  centre: 'central',
}

function TurnRecord({ game, deployment, onError }) {
  const [record, setRecord] = useState(null)

  useEffect(() => {
    if (game.status !== 'in_progress') {
      setRecord(null)
      return
    }
    let cancelled = false
    getTurnRecord(game.id)
      .then((r) => !cancelled && setRecord(r))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
    // Again whenever the battlefield changes (models destroyed).
  }, [game, deployment])

  if (!record) return null
  const nameOf = (seat) => game.players.find((p) => p.seat === seat)?.user_name ?? 'No one'
  const unitName = (id) => deployment?.units.find((u) => u.unit_id === id)?.name ?? 'a unit'
  const destroyedUnits = record.destroyed.filter((d) => d.unit_destroyed)

  return (
    <CardTextAccordion
      className="turn-record"
      label={`Turn record: battle round ${record.battle_round}, ${nameOf(record.turn_seat)}'s turn · ${
        record.destroyed.length
      } ${record.destroyed.length === 1 ? 'model' : 'models'} destroyed`}
    >
      <h4>Destroyed this turn</h4>
      {record.destroyed.length === 0 ? (
        <p className="hint">Nothing yet.</p>
      ) : (
        <ul className="round-start-rules">
          {record.destroyed.map((d, i) => (
            <li key={i}>
              {d.model_name} ({d.unit_name}, {nameOf(d.seat)})
              <span className="hint">
                {' '}
                · {d.phase ?? ''} · {d.destroyed_by ? `by ${d.destroyed_by}` : 'not by an enemy'}
                {d.unit_destroyed && ' · unit destroyed'}
              </span>
            </li>
          ))}
        </ul>
      )}
      {destroyedUnits.length > 0 && (
        <p>
          <strong>Units destroyed:</strong>{' '}
          {destroyedUnits.map((d) => `${d.unit_name} (${nameOf(d.seat)})`).join(', ')}
        </p>
      )}
      <h4>At the start of the turn</h4>
      {record.start.length === 0 ? (
        <p className="hint">Not recorded.</p>
      ) : (
        <ul className="round-start-rules">
          {record.start.map((o) => (
            <li key={o.objective_id}>
              {KIND_NAMES[o.kind] ?? o.kind} objective:{' '}
              {o.controller === null ? 'not controlled' : `controlled by ${nameOf(o.controller)}`}
              {o.unit_ids.length > 0 && (
                <span className="hint"> · on it: {o.unit_ids.map(unitName).join(', ')}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </CardTextAccordion>
  )
}

export default TurnRecord
