import { useEffect, useState } from 'react'
import { listDispositions } from '../api'
import { listPoints } from '../listPoints'
import FactionFilter from './FactionFilter'
import { DeleteButton, EditButton } from './IconButtons'

function ListsListPage({
  lists,
  factions,
  factionFilter,
  onFactionFilterChange,
  detachments,
  units,
  enhancements,
  error,
  onEdit,
  onAddNew,
  onDelete,
}) {
  const [dispositions, setDispositions] = useState([])
  useEffect(() => {
    listDispositions()
      .then(setDispositions)
      .catch(() => setDispositions([]))
  }, [])
  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
  // A list's disposition: the one chosen, or the only one its detachments
  // offer (what its games use).
  const dispositionOf = (l) => {
    const offered = [
      ...new Set(
        detachments
          .filter((d) => l.detachment_ids.includes(d.id))
          .flatMap((d) => d.disposition_ids ?? [])
      ),
    ]
    const id = l.disposition_id ?? (offered.length === 1 ? offered[0] : null)
    return dispositions.find((d) => d.id === id)?.name ?? null
  }
  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const visibleLists = lists.filter(
    (l) => factionFilter === '' || String(l.faction_id) === factionFilter
  )

  return (
    <section>
      <h2>Lists</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add List
      </button>
      <FactionFilter
        factions={factions}
        items={lists}
        value={factionFilter}
        onChange={onFactionFilterChange}
      />
      <ul>
        {visibleLists.map((l) => (
          <li key={l.id} className="list-entry">
            <div>
              {factionName(l.faction_id)} - {l.name} (
              {listPoints(
                units.filter((u) => u.list_id === l.id),
                enhancements
              )}
              /{l.points_limit})
            </div>
            {l.detachment_ids.length > 0 && (
              <div>[{l.detachment_ids.map(detachmentName).join(', ')}]</div>
            )}
            {dispositionOf(l) && <div>{dispositionOf(l)}</div>}
            <div className="list-entry__actions">
              <EditButton onClick={() => onEdit(l)} />
              <DeleteButton onClick={() => onDelete(l.id)} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ListsListPage
