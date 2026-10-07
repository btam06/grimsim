function ListsListPage({
  lists,
  factions,
  detachments,
  units,
  models,
  weapons,
  wargear,
  factionUnits,
  error,
  onEdit,
  onAddNew,
  onDelete,
}) {
  const factionName = (id) => factions.find((f) => f.id === id)?.name ?? `#${id}`
  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const factionUnitName = (id) => factionUnits.find((fu) => fu.id === id)?.name ?? `#${id}`
  const unitsForList = (listId) => units.filter((u) => u.list_id === listId)

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
            {l.name} — {l.points_limit}pts, {factionName(l.faction_id)}
            {l.detachment_ids.length > 0 &&
              `, ${l.detachment_ids.map(detachmentName).join(', ')}`}
            <button type="button" onClick={() => onEdit(l)}>
              Edit
            </button>
            <button type="button" onClick={() => onDelete(l.id)}>
              Delete
            </button>
            {unitsForList(l.id).length > 0 && (
              <ul>
                {unitsForList(l.id).map((u) => (
                  <li key={u.id}>
                    {factionUnitName(u.faction_unit_id)} — {u.points}pts
                    {u.unit_models.length > 0 && (
                      <ul>
                        {u.unit_models.map((um) => (
                          <li key={um.id}>
                            {modelName(um.model_id)}
                            {um.weapon_ids.length > 0 &&
                              ` — Weapons: ${um.weapon_ids.map(weaponName).join(', ')}`}
                            {um.wargear_ids.length > 0 &&
                              ` — Wargear: ${um.wargear_ids.map(wargearName).join(', ')}`}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ListsListPage
