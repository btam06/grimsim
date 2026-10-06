import AddWeaponForm from './AddWeaponForm'

function ModelsListPage({ models, abilities, weapons, weaponAbilities, error, onEdit, onAddNew, onWeaponAdded }) {
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`

  return (
    <section>
      <h2>Models</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add Model
      </button>
      <ul>
        {models.map((m) => (
          <li key={m.id}>
            <div>
              #{m.id} {m.name} — {m.points}pts, M{m.movement}" T{m.toughness} Sv{m.save}+ W{m.wounds}{' '}
              OC{m.oc}
              {m.invulnerable ? ` Inv${m.invulnerable}+` : ''}
              {m.feel_no_pain ? ` FNP${m.feel_no_pain}+` : ''}
              {m.ability_ids.length > 0 &&
                ` — Abilities: ${m.ability_ids.map(abilityName).join(', ')}`}
              {m.weapon_ids.length > 0 && ` — Weapons: ${m.weapon_ids.map(weaponName).join(', ')}`}
              <button type="button" onClick={() => onEdit(m)}>
                Edit
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ModelsListPage
