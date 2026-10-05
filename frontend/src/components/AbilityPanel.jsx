import { useEffect, useState } from 'react'

function AbilityPanel({ title, listFn, createFn }) {
  const [items, setItems] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listFn().then(setItems).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createFn({ name, description: description || null })
      setName('')
      setDescription('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>{title}</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="submit">Add</button>
      </form>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            #{item.id} {item.name}
            {item.description ? ` — ${item.description}` : ''}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default AbilityPanel
