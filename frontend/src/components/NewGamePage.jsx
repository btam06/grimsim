import { useEffect, useState } from 'react'
import {
  createGame,
  listDetachments,
  listDispositions,
  listLists,
  listSecondaryMissions,
  listUsers,
} from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'
import Select from './Select'

const EMPTY_PLAYER = {
  user_id: '',
  list_id: '',
  secondary_mode: 'tactical',
  fixed_secondary_ids: [],
}

function NewGamePage({ onCreated, onCancel }) {
  const [users, setUsers] = useState([])
  const [lists, setLists] = useState([])
  const [detachments, setDetachments] = useState([])
  const [dispositions, setDispositions] = useState([])
  const [secondaries, setSecondaries] = useState([])
  const [players, setPlayers] = useState([EMPTY_PLAYER, EMPTY_PLAYER])
  const [attackerSeat, setAttackerSeat] = useState(1)
  const [error, setError] = useState(null)

  useEffect(() => {
    listUsers().then(setUsers).catch((err) => setError(err.message))
    listLists().then(setLists).catch((err) => setError(err.message))
    listDetachments().then(setDetachments).catch((err) => setError(err.message))
    listDispositions().then(setDispositions).catch((err) => setError(err.message))
    listSecondaryMissions().then(setSecondaries).catch((err) => setError(err.message))
  }, [])

  const update = (index, changes) =>
    setPlayers(players.map((p, i) => (i === index ? { ...p, ...changes } : p)))

  // A player's disposition: their list's (chosen on the list), or the only
  // one its detachments offer - undefined if it has to be chosen there.
  const dispositionOf = (player) => {
    const list = lists.find((l) => String(l.id) === player.list_id)
    if (!list) return null
    if (list.disposition_id != null) return dispositions.find((d) => d.id === list.disposition_id)
    const ids = new Set(
      detachments
        .filter((d) => list.detachment_ids.includes(d.id))
        .flatMap((d) => d.disposition_ids)
    )
    const offered = dispositions.filter((d) => ids.has(d.id))
    return offered.length === 1 ? offered[0] : offered.length === 0 ? null : undefined
  }
  const fixedOptions = secondaries
    .filter((m) => m.fixed_points !== null)
    .map((m) => ({ id: m.id, name: `${m.name} (${m.fixed_points} VP)` }))

  const seatName = (seat) =>
    users.find((u) => String(u.id) === players[seat - 1].user_id)?.name ?? `Player ${seat}`
  const seatOptions = [1, 2].map((seat) => ({ id: seat, name: seatName(seat) }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (players.some((p) => !p.user_id || !p.list_id)) {
      setError('Each player needs a user and a list')
      return
    }
    try {
      const game = await createGame({
        players: players.map((p) => ({
          user_id: Number(p.user_id),
          list_id: Number(p.list_id),
          secondary_mode: p.secondary_mode,
          fixed_secondary_ids: p.secondary_mode === 'fixed' ? p.fixed_secondary_ids : [],
        })),
        // Who goes first is rolled off once everything is set up.
        attacker_seat: Number(attackerSeat),
      })
      onCreated(game)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>New Game</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        {players.map((player, index) => {
          const userLists = lists.filter((l) => String(l.user_id) === player.user_id)
          const disposition = dispositionOf(player)
          return (
            <fieldset key={index} className="form-section">
              <legend>Player {index + 1}</legend>
              <Field label="User">
                <Select
                  options={users}
                  value={player.user_id}
                  onChange={(user_id) => update(index, { user_id, list_id: '' })}
                  placeholder="Select user"
                />
              </Field>
              <Field label="List">
                <Select
                  options={userLists}
                  value={player.list_id}
                  onChange={(list_id) => update(index, { list_id })}
                  placeholder={player.user_id ? 'Select list' : 'Select a user first'}
                />
              </Field>
              {disposition && <p className="hint">Disposition: {disposition.name}</p>}
              {disposition === undefined && (
                <p className="error">Choose the list's disposition (on the list) first.</p>
              )}
              <div className="radio-group">
                Secondaries
                {['tactical', 'fixed'].map((mode) => (
                  <label key={mode} className="radio-option">
                    <input
                      type="radio"
                      name={`secondary-mode-${index}`}
                      checked={player.secondary_mode === mode}
                      onChange={() => update(index, { secondary_mode: mode })}
                    />
                    {mode === 'tactical' ? 'Tactical' : 'Fixed'}
                  </label>
                ))}
              </div>
              {player.secondary_mode === 'fixed' && (
                <label className="field">
                  Fixed secondaries (pick 2)
                  <MultiSelect
                    options={fixedOptions}
                    value={player.fixed_secondary_ids}
                    onChange={(fixed_secondary_ids) => update(index, { fixed_secondary_ids })}
                  />
                </label>
              )}
            </fieldset>
          )
        })}
        <Field label="Attacker">
          <Select options={seatOptions} value={String(attackerSeat)} onChange={setAttackerSeat} />
        </Field>
        <button type="submit">Create Game</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>
    </section>
  )
}

export default NewGamePage
