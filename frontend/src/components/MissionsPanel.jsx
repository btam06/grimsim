import { useEffect, useState } from 'react'
import {
  createPrimaryMission,
  createSecondaryMission,
  deletePrimaryMission,
  deleteSecondaryMission,
  listDispositions,
  listPrimaryMissions,
  listSecondaryMissions,
} from '../api'
import Field from './Field'
import { DeleteButton } from './IconButtons'
import Select from './Select'

const COMPLETES_ON = [
  { id: 'your_turn', name: 'Your turn' },
  { id: 'opponent_turn', name: "Opponent's turn" },
  { id: 'either', name: 'Either turn' },
]
const completesOnLabel = (value) => COMPLETES_ON.find((o) => o.id === value)?.name ?? value

function SecondaryMissions() {
  const [missions, setMissions] = useState([])
  const [form, setForm] = useState({
    name: '',
    description: '',
    completes_on: 'your_turn',
    fixed_points: '',
    tactical_points: '',
  })
  const [error, setError] = useState(null)

  const refresh = () =>
    listSecondaryMissions()
      .then(setMissions)
      .catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createSecondaryMission({
        name: form.name,
        description: form.description || null,
        completes_on: form.completes_on,
        fixed_points: form.fixed_points === '' ? null : Number(form.fixed_points),
        tactical_points: form.tactical_points === '' ? null : Number(form.tactical_points),
      })
      setForm({ ...form, name: '', description: '', fixed_points: '', tactical_points: '' })
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deleteSecondaryMission(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const pointsLabel = (points) => (points === null ? 'not available' : `${points} VP`)

  return (
    <section>
      <h2>Secondary Missions</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={form.name} onChange={handleChange('name')} required />
        </Field>
        <Field label="Completes on">
          <Select
            options={COMPLETES_ON}
            value={form.completes_on}
            onChange={(completes_on) => setForm({ ...form, completes_on })}
          />
        </Field>
        <Field label="Fixed VP (blank if not usable as fixed)">
          <input
            type="number"
            min="0"
            value={form.fixed_points}
            onChange={handleChange('fixed_points')}
          />
        </Field>
        <Field label="Tactical VP (blank if not usable as tactical)">
          <input
            type="number"
            min="0"
            value={form.tactical_points}
            onChange={handleChange('tactical_points')}
          />
        </Field>
        <label className="field">
          Description (optional)
          <textarea value={form.description} onChange={handleChange('description')} rows={3} />
        </label>
        <button type="submit">Add Secondary Mission</button>
      </form>
      <ul>
        {missions.map((m) => (
          <li key={m.id}>
            {m.name} — completes on {completesOnLabel(m.completes_on).toLowerCase()} — Fixed:{' '}
            {pointsLabel(m.fixed_points)}, Tactical: {pointsLabel(m.tactical_points)}
            <DeleteButton onClick={() => handleDelete(m.id)} />
            {m.description && <p className="hint card-text">{m.description}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function PrimaryMissions() {
  const [missions, setMissions] = useState([])
  const [dispositions, setDispositions] = useState([])
  const [form, setForm] = useState({
    name: '',
    description: '',
    player_disposition_id: '',
    opponent_disposition_id: '',
  })
  const [error, setError] = useState(null)

  const refresh = () =>
    listPrimaryMissions()
      .then(setMissions)
      .catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listDispositions()
      .then(setDispositions)
      .catch((err) => setError(err.message))
  }, [])

  const dispositionName = (id) => dispositions.find((d) => d.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!form.player_disposition_id || !form.opponent_disposition_id) {
      setError('Both dispositions are required')
      return
    }
    try {
      await createPrimaryMission({
        name: form.name,
        description: form.description || null,
        player_disposition_id: Number(form.player_disposition_id),
        opponent_disposition_id: Number(form.opponent_disposition_id),
      })
      setForm({ ...form, name: '', description: '' })
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deletePrimaryMission(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Primary Missions</h2>
      <p className="hint">A player's primary mission is the one for their disposition against their opponent's.</p>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </Field>
        <Field label="Your disposition">
          <Select
            options={dispositions}
            value={form.player_disposition_id}
            onChange={(player_disposition_id) => setForm({ ...form, player_disposition_id })}
            placeholder="Select disposition"
          />
        </Field>
        <Field label="Opponent's disposition">
          <Select
            options={dispositions}
            value={form.opponent_disposition_id}
            onChange={(opponent_disposition_id) => setForm({ ...form, opponent_disposition_id })}
            placeholder="Select disposition"
          />
        </Field>
        <label className="field">
          Description (optional)
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
          />
        </label>
        <button type="submit">Add Primary Mission</button>
      </form>
      <ul>
        {missions.map((m) => (
          <li key={m.id}>
            {m.name} — {dispositionName(m.player_disposition_id)} vs{' '}
            {dispositionName(m.opponent_disposition_id)}
            <DeleteButton onClick={() => handleDelete(m.id)} />
            {m.description && <p className="hint card-text">{m.description}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export { PrimaryMissions, SecondaryMissions }
