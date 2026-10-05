import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState(null)
  const [items, setItems] = useState([])
  const [name, setName] = useState('')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
    refreshItems()
  }, [])

  const refreshItems = () => {
    fetch('/api/items')
      .then((r) => r.json())
      .then(setItems)
  }

  const addItem = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    await fetch('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    setName('')
    refreshItems()
  }

  return (
    <div className="app">
      <h1>Grimsim</h1>
      <p>API status: {health ? health.status : 'checking...'}</p>
      <form onSubmit={addItem}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New item name"
        />
        <button type="submit">Add</button>
      </form>
      <ul>
        {items.map((item) => (
          <li key={item.id}>{item.name}</li>
        ))}
      </ul>
    </div>
  )
}

export default App
