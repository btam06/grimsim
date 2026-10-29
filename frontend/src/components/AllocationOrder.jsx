import { useEffect, useState } from 'react'
import { getAllocationGroups } from '../api'

// The defending player's order for their unit's allocation groups (05.03):
// attacks go to the first group until it's gone, then the next. The rules
// fix some of it - a wounded non-CHARACTER group goes first, CHARACTER groups
// last - and the rest is theirs to order (see app/services/combat.py's
// _Allocation). `order` is the group ids, in order; `onChange` gets a new one.
function AllocationOrder({ gameId, unitId, defender, order, onChange }) {
  const [groups, setGroups] = useState([])

  useEffect(() => {
    setGroups([])
    if (!unitId) return
    let cancelled = false
    getAllocationGroups(gameId, unitId)
      .then((g) => {
        if (cancelled) return
        setGroups(g)
        onChange(g.map((group) => group.id))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [gameId, unitId])

  if (groups.length < 2) return null
  const byId = Object.fromEntries(groups.map((g) => [g.id, g]))
  const ordered = (order.length ? order : groups.map((g) => g.id)).filter((id) => byId[id])
  const move = (i, by) => {
    const next = [...ordered]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    onChange(next)
  }
  const label = (g) => {
    const counts = {}
    for (const name of g.model_names) counts[name] = (counts[name] ?? 0) + 1
    const names = Object.entries(counts)
      .map(([name, n]) => (n > 1 ? `${n}× ${name}` : name))
      .join(', ')
    return `${names}${g.character ? ' (CHARACTER)' : ''}${g.wounded ? ' (wounded)' : ''}`
  }
  return (
    <details className="allocation-order">
      <summary>
        Allocation order <span className="hint">· {defender ?? 'the defender'} picks</span>
      </summary>
      <ol>
        {ordered.map((id, i) => (
          <li key={id}>
            {label(byId[id])}{' '}
            <button type="button" disabled={i === 0} onClick={() => move(i, -1)}>
              ↑
            </button>
            <button type="button" disabled={i === ordered.length - 1} onClick={() => move(i, 1)}>
              ↓
            </button>
          </li>
        ))}
      </ol>
      <p className="hint">
        A wounded group goes first and CHARACTER groups last whatever the order (05.03).
      </p>
    </details>
  )
}

export default AllocationOrder
