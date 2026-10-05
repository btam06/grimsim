import { useEffect, useState } from 'react'
import { createModel, listModels } from '../api'

const EMPTY_FORM = {
  name: '',
  faction_id: '',
  points: '',
  save: '',
  toughness: '',
  oc: '',
  movement: '',
  wounds: '',
  invulnerable: '',
  feel_no_pain: '',
}

function toPayload(form) {
  return {
    name: form.name,
    faction_id: Number(form.faction_id),
    points: Number(form.points),
    save: Number(form.save),
    toughness: Number(form.toughness),
    oc: Number(form.oc),
    movement: Number(form.movement),
    wounds: Number(form.wounds),
    invulnerable: form.invulnerable === '' ? null : Number(form.invulnerable),
    feel_no_pain: form.feel_no_pain === '' ? null : Number(form.feel_no_pain),
  }
}

function ModelsPanel() {
  const [models, setModels] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState(null)

  const refresh = () => listModels().then(setModels).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createModel(toPayload(form))
      setForm(EMPTY_FORM)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Models</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <input placeholder="Name" value={form.name} onChange={handleChange('name')} required />
        <input
          placeholder="Faction ID"
          type="number"
          value={form.faction_id}
          onChange={handleChange('faction_id')}
          required
        />
        <input
          placeholder="Points"
          type="number"
          value={form.points}
          onChange={handleChange('points')}
          required
        />
        <input
          placeholder="Save"
          type="number"
          value={form.save}
          onChange={handleChange('save')}
          required
        />
        <input
          placeholder="Toughness"
          type="number"
          value={form.toughness}
          onChange={handleChange('toughness')}
          required
        />
        <input placeholder="OC" type="number" value={form.oc} onChange={handleChange('oc')} required />
        <input
          placeholder="Movement"
          type="number"
          value={form.movement}
          onChange={handleChange('movement')}
          required
        />
        <input
          placeholder="Wounds"
          type="number"
          value={form.wounds}
          onChange={handleChange('wounds')}
          required
        />
        <input
          placeholder="Invulnerable (optional)"
          type="number"
          value={form.invulnerable}
          onChange={handleChange('invulnerable')}
        />
        <input
          placeholder="Feel No Pain (optional)"
          type="number"
          value={form.feel_no_pain}
          onChange={handleChange('feel_no_pain')}
        />
        <button type="submit">Add Model</button>
      </form>
      <ul>
        {models.map((m) => (
          <li key={m.id}>
            #{m.id} {m.name} — {m.points}pts, M{m.movement}" T{m.toughness} Sv{m.save}+ W{m.wounds} OC
            {m.oc}
            {m.invulnerable ? ` Inv${m.invulnerable}+` : ''}
            {m.feel_no_pain ? ` FNP${m.feel_no_pain}+` : ''}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ModelsPanel
