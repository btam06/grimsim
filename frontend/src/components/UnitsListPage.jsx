function UnitsListPage({
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
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const factionUnitName = (id) => factionUnits.find((fu) => fu.id === id)?.name ?? `#${id}`

  return (
    <section>
      <h2>Units</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add Unit
      </button>
      <ul>
        {units.map((u) => (
          <li key={u.id}>
            {factionUnitName(u.faction_unit_id)} — {u.points}pts —{' '}
            {u.unit_models.length === 0
              ? 'no models'
              : u.unit_models
                  .map((um) => {
                    const parts = [modelName(um.model_id)]
                    if (um.weapon_ids.length > 0) parts.push(um.weapon_ids.map(weaponName).join('/'))
                    if (um.wargear_ids.length > 0) parts.push(um.wargear_ids.map(wargearName).join('/'))
                    return parts.join(' — ')
                  })
                  .join('; ')}
            <button type="button" onClick={() => onEdit(u)}>
              Edit
            </button>
            <button type="button" onClick={() => onDelete(u.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default UnitsListPage
