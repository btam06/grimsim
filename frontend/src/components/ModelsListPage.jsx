function ModelsListPage({ models, abilities, weapons, wargear, error, onEdit, onAddNew }) {
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`

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
              {m.name} — M{m.movement}" T{m.toughness} Sv{m.save}+ W{m.wounds} OC{m.oc}
              {m.invulnerable ? ` Inv${m.invulnerable}+` : ''}
              {m.feel_no_pain ? ` FNP${m.feel_no_pain}+` : ''}
              {m.ability_ids.length > 0 &&
                ` — Abilities: ${m.ability_ids.map(abilityName).join(', ')}`}
              {m.weapon_ids.length > 0 && ` — Weapons: ${m.weapon_ids.map(weaponName).join(', ')}`}
              {m.wargear_ids.length > 0 &&
                ` — Wargear: ${m.wargear_ids.map(wargearName).join(', ')}`}
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
