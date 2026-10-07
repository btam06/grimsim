import { skillLabel } from '../weaponDisplay'

function WeaponsListPage({ weapons, models, abilities, error, onEdit, onAddNew, onDelete }) {
  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`

  return (
    <section>
      <h2>Weapons</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add Weapon
      </button>
      <ul>
        {weapons.map((w) => (
          <li key={w.id}>
            {w.name} ({modelName(w.model_id)}) —{w.range !== null ? ` R${w.range}"` : ''} A
            {w.attacks} S{w.strength} AP{w.ap} D{w.damage} {skillLabel(w.weapon_type)}
            {w.skill}+
            {w.ability_ids.length > 0 && ` — ${w.ability_ids.map(abilityName).join(', ')}`}
            <button type="button" onClick={() => onEdit(w)}>
              Edit
            </button>
            <button type="button" onClick={() => onDelete(w.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default WeaponsListPage
