import { skillLabel } from '../weaponDisplay'
import FactionFilter from './FactionFilter'
import { EditButton } from './IconButtons'

function ModelsListPage({
  models,
  factions,
  factionFilter,
  onFactionFilterChange,
  abilities,
  keywords,
  baseSizes,
  factionAbilities,
  weapons,
  wargear,
  error,
  onEdit,
  onAddNew,
}) {
  const abilityName = (id) => abilities.find((a) => a.id === id)?.name ?? `#${id}`
  const baseSizeName = (id) => baseSizes.find((b) => b.id === id)?.name ?? `#${id}`
  const keywordName = (id) => keywords.find((k) => k.id === id)?.name ?? `#${id}`
  const factionAbilityName = (id) => factionAbilities.find((a) => a.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`
  const weaponsFor = (modelId) => weapons.filter((w) => w.model_id === modelId)
  const visibleModels = models.filter(
    (m) => factionFilter === '' || String(m.faction_id) === factionFilter
  )

  return (
    <section>
      <h2>Models</h2>
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={onAddNew}>
        + Add Model
      </button>
      <FactionFilter
        factions={factions}
        items={models}
        value={factionFilter}
        onChange={onFactionFilterChange}
      />
      <ul>
        {visibleModels.map((m) => (
          <li key={m.id}>
            <div>
              {m.name} — M{m.movement}" T{m.toughness} Sv{m.save}+ W{m.wounds} OC{m.oc} Ld
              {m.leadership}+
              {m.invulnerable ? ` Inv${m.invulnerable}+` : ''}
              {m.feel_no_pain ? ` FNP${m.feel_no_pain}+` : ''}
              {m.base_size_id !== null && ` — Base: ${baseSizeName(m.base_size_id)}`}
              {m.is_support ? ' [Support]' : ''}
              {m.is_leader ? ' [Leader]' : ''}
              {m.keyword_ids.length > 0 &&
                ` — Keywords: ${m.keyword_ids.map(keywordName).join(', ')}`}
              {m.faction_ability_ids.length > 0 &&
                ` — Faction Abilities: ${m.faction_ability_ids.map(factionAbilityName).join(', ')}`}
              {m.ability_ids.length > 0 &&
                ` — Abilities: ${m.ability_ids.map(abilityName).join(', ')}`}
              {m.wargear_ids.length > 0 &&
                ` — Wargear: ${m.wargear_ids.map(wargearName).join(', ')}`}
              <EditButton onClick={() => onEdit(m)} />
            </div>
            {weaponsFor(m.id).length > 0 && (
              <ul>
                {weaponsFor(m.id).map((w) => (
                  <li key={w.id}>
                    {w.name} —{w.range !== null ? ` R${w.range}"` : ''} A{w.attacks} S{w.strength} AP
                    {w.ap} D{w.damage} {skillLabel(w.weapon_type)}
                    {w.skill}+
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

export default ModelsListPage
