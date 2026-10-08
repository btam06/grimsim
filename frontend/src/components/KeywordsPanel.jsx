import { useEffect, useState } from 'react'
import { createKeyword, deleteKeyword, listKeywords } from '../api'
import Field from './Field'

function KeywordsPanel() {
  const [keywords, setKeywords] = useState([])
  const [name, setName] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listKeywords().then(setKeywords).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createKeyword({ name })
      setName('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteKeyword(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Keywords</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <button type="submit">Add Keyword</button>
      </form>
      <ul>
        {keywords.map((k) => (
          <li key={k.id}>
            {k.name}
            <button type="button" onClick={() => handleRemove(k.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default KeywordsPanel
