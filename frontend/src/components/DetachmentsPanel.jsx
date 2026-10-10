import { useEffect, useState } from 'react'
import {
  createDetachment,
  deleteDetachment,
  listDetachments,
  listDispositions,
  listFactions,
} from '../api'
import Field from './Field'
import MultiSelect from './MultiSelect'
import Select from './Select'

function DetachmentsPanel() {
  const [detachments, setDetachments] = useState([])
  const [factions, setFactions] = useState([])
  const [dispositions, setDispositions] = useState([])
  const [name, setName] = useState('')
  const [factionId, setFactionId] = useState('')
  const [dp, setDp] = useState('')
  const [dispositionIds, setDispositionIds] = useState([])
  const [error, setError] = useState(null)

  const refresh = () => listDetachments().then(setDetachments).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listFactions().then(setFactions).catch((err) => setError(err.message))
    listDispositions()
      .then(setDispositions)
      .catch((err) => setError(err.message))
  }, [])

  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
  const dispositionName = (id) => dispositions.find((d) => d.id === id)?.name ?? `#${id}`

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!factionId) {
      setError('Faction is required')
      return
    }
    try {
      await createDetachment({
        name,
        faction_id: Number(factionId),
        dp: Number(dp),
        disposition_ids: dispositionIds,
      })
      setName('')
      setFactionId('')
      setDp('')
      setDispositionIds([])
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteDetachment(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Detachments</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Faction">
          <Select options={factions} value={factionId} onChange={setFactionId} placeholder="Select faction" />
        </Field>
        <Field label="DP">
          <input type="number" value={dp} onChange={(e) => setDp(e.target.value)} required />
        </Field>
        <label className="field">
          Dispositions
          <MultiSelect
            options={dispositions}
            value={dispositionIds}
            onChange={setDispositionIds}
          />
        </label>
        <button type="submit">Add Detachment</button>
      </form>
      <ul>
        {detachments.map((d) => (
          <li key={d.id}>
            {d.name} ({factionName(d.faction_id)}) — DP {d.dp}
            {d.disposition_ids.length > 0 &&
              ` — ${d.disposition_ids.map(dispositionName).join(', ')}`}
            <button type="button" onClick={() => handleRemove(d.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default DetachmentsPanel
