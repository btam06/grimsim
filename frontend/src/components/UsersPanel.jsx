import { useEffect, useState } from 'react'
import { createUser, deleteUser, listUsers } from '../api'
import Field from './Field'
import { DeleteButton } from './IconButtons'

function UsersPanel() {
  const [users, setUsers] = useState([])
  const [name, setName] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listUsers().then(setUsers).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await createUser({ name })
      setName('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deleteUser(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Users</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <button type="submit">Add User</button>
      </form>
      <ul>
        {users.map((u) => (
          <li key={u.id}>
            {u.name}
            <DeleteButton onClick={() => handleDelete(u.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default UsersPanel
