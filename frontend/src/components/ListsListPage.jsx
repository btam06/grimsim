function ListsListPage({ lists, factions, detachments, units, error, onEdit, onAddNew }) {
  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const unitName = (id) => units.find((u) => u.id === id)?.name ?? `#${id}`

  return (
    <section>
      <h2>Lists</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add List
      </button>
      <ul>
        {lists.map((l) => (
          <li key={l.id}>
            {l.name} — {l.points_limit}pts, {factionName(l.faction_id)},{' '}
            {detachmentName(l.detachment_id)}
            {l.unit_ids.length > 0 && ` — Units: ${l.unit_ids.map(unitName).join(', ')}`}
            <button type="button" onClick={() => onEdit(l)}>
              Edit
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ListsListPage
