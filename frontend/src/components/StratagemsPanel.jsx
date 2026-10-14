import { useEffect, useState } from 'react'
import {
  createStratagem,
  deleteStratagem,
  listConditions,
  listDetachments,
  listEffects,
  listStratagems,
} from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'

function StratagemsPanel() {
  const [stratagems, setStratagems] = useState([])
  const [detachments, setDetachments] = useState([])
  const [conditions, setConditions] = useState([])
  const [effects, setEffects] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [cp, setCp] = useState('1')
  const [isCore, setIsCore] = useState(false)
  const [detachmentIds, setDetachmentIds] = useState([])
  const [conditionIds, setConditionIds] = useState([])
  const [effectIds, setEffectIds] = useState([])
  const [error, setError] = useState(null)

  const refresh = () => listStratagems().then(setStratagems).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listDetachments().then(setDetachments).catch((err) => setError(err.message))
    listConditions().then(setConditions).catch((err) => setError(err.message))
    listEffects().then(setEffects).catch((err) => setError(err.message))
  }, [])

  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const conditionName = (id) => conditions.find((c) => c.id === id)?.name ?? `#${id}`
  const effectName = (id) => effects.find((e) => e.id === id)?.name ?? `#${id}`

  const toggleId = (list, setList, id) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!isCore && detachmentIds.length === 0) {
      setError('Select at least one detachment, or mark the stratagem as core')
      return
    }
    try {
      await createStratagem({
        name,
        description: description || null,
        cp: Number(cp),
        is_core: isCore,
        detachment_ids: isCore ? [] : detachmentIds,
        condition_ids: conditionIds,
        effect_ids: effectIds,
      })
      setName('')
      setDescription('')
      setCp('1')
      setIsCore(false)
      setDetachmentIds([])
      setConditionIds([])
      setEffectIds([])
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteStratagem(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Stratagems</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="CP">
          <input type="number" min="0" value={cp} onChange={(e) => setCp(e.target.value)} required />
        </Field>
        <label className="checkbox-field">
          <input type="checkbox" checked={isCore} onChange={(e) => setIsCore(e.target.checked)} />
          Core stratagem (usable with any detachment)
        </label>
        {!isCore && (
          <label className="field">
            Detachments
            <MultiSelect options={detachments} value={detachmentIds} onChange={setDetachmentIds} />
          </label>
        )}
        <div className="checkbox-group">
          Conditions
          <div className="checkbox-grid">
            {conditions.map((c) => (
              <label key={c.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={conditionIds.includes(c.id)}
                  onChange={() => toggleId(conditionIds, setConditionIds, c.id)}
                />
                {c.name}
              </label>
            ))}
          </div>
        </div>
        <div className="checkbox-group">
          Effects
          <div className="checkbox-grid">
            {effects.map((e) => (
              <label key={e.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={effectIds.includes(e.id)}
                  onChange={() => toggleId(effectIds, setEffectIds, e.id)}
                />
                {e.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit">Add Stratagem</button>
      </form>
      <ul>
        {stratagems.map((s) => (
          <li key={s.id}>
            {s.name} — {s.cp} CP —{' '}
            {s.is_core ? 'Core' : s.detachment_ids.map(detachmentName).join(', ')}
            {s.description ? ` — ${s.description}` : ''}
            {s.condition_ids.length > 0 &&
              ` — Conditions: ${s.condition_ids.map(conditionName).join(', ')}`}
            {s.effect_ids.length > 0 && ` — Effects: ${s.effect_ids.map(effectName).join(', ')}`}
            <button type="button" onClick={() => handleRemove(s.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default StratagemsPanel
