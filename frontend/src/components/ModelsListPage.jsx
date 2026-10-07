function ModelsListPage({ models, abilities, weapons, wargear, error, onEdit, onAddNew }) {
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const weaponsFor = (modelId) => weapons.filter((w) => w.model_id === modelId)

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
              {m.name} — M{m.movement}" T{m.toughness} Sv{m.save}+ W{m.wounds} OC{m.oc} Ld
              {m.leadership}+
              {m.invulnerable ? ` Inv${m.invulnerable}+` : ''}
              {m.feel_no_pain ? ` FNP${m.feel_no_pain}+` : ''}
              {m.is_support ? ' [Support]' : ''}
              {m.is_leader ? ' [Leader]' : ''}
              {m.ability_ids.length > 0 &&
                ` — Abilities: ${m.ability_ids.map(abilityName).join(', ')}`}
              {weaponsFor(m.id).length > 0 &&
                ` — Weapons: ${weaponsFor(m.id)
                  .map((w) => w.name)
                  .join(', ')}`}
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
