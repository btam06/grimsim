import FactionFilter from './FactionFilter'
import { DeleteButton, EditButton } from './IconButtons'

function ListsListPage({
  lists,
  factions,
  factionFilter,
  onFactionFilterChange,
  detachments,
  error,
  onEdit,
  onAddNew,
  onDelete,
}) {
  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
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
          <li key={l.id}>
            {l.name} — {l.points_limit}pts, {factionName(l.faction_id)}
            {l.detachment_ids.length > 0 &&
              `, ${l.detachment_ids.map(detachmentName).join(', ')}`}
            <EditButton onClick={() => onEdit(l)} />
            <DeleteButton onClick={() => onDelete(l.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ListsListPage
