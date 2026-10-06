import { useEffect, useState } from 'react'
import {
  createDetachment,
  deleteDetachment,
  listDetachments,
  listDispositions,
  listFactions,
} from '../api'
import MultiSelect from './MultiSelect'

function DetachmentsPanel() {
  const [detachments, setDetachments] = useState([])
  const [factions, setFactions] = useState([])
  const [dispositions, setDispositions] = useState([])
  const [name, setName] = useState('')
  const [factionId, setFactionId] = useState('')
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
    try {
      await createDetachment({
        name,
        faction_id: Number(factionId),
        disposition_ids: dispositionIds,
      })
      setName('')
      setFactionId('')
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
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <select value={factionId} onChange={(e) => setFactionId(e.target.value)} required>
          <option value="" disabled>
            Select faction
          </option>
          {factions.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
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
            {d.name} ({factionName(d.faction_id)})
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
