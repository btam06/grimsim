import { skillValue } from '../weaponDisplay'
import CardTextAccordion from './CardTextAccordion'

// A unit's datasheet as it's been built - each kind of model in it with its
// profile, the weapons and wargear those models are equipped with (and any
// weapons their enhancements give them), their abilities and keywords - plus
// any enhancement or upgrade the unit has. Collapsed under a "Datasheet" label.
function UnitDatasheet({ unit, data }) {
  if (!unit) return null
  const {
    models,
    weapons,
    wargear,
    weaponAbilities,
    datasheetAbilities,
    factionAbilities,
    keywords,
    baseSizes,
    enhancements,
  } = data
  const nameOf = (list, id) => list.find((x) => x.id === id)?.name ?? `#${id}`

  // Each kind of model once, in the order it first appears, with its count.
  const counts = new Map()
  unit.unit_models.forEach((um) => counts.set(um.model_id, (counts.get(um.model_id) ?? 0) + 1))
  const carried = unit.unit_models
    .filter((um) => um.enhancement_id !== null)
    .map((um) => enhancements.find((e) => e.id === um.enhancement_id))
    .filter(Boolean)
  const upgrade = enhancements.find((e) => e.id === unit.upgrade_id)

  return (
    <CardTextAccordion label="Datasheet" className="datasheet-accordion">
      <div className="datasheet">
        {[...counts.entries()].map(([modelId, count]) => {
          const model = models.find((m) => m.id === modelId)
          if (!model) return null
          const unitModels = unit.unit_models.filter((um) => um.model_id === modelId)
          // Each weapon these models carry once, with how many carry it -
          // including any their enhancements give them.
          const carriedWeapons = new Map()
          const carry = (weapon) => {
            const entry = carriedWeapons.get(weapon.id) ?? { weapon, count: 0 }
            entry.count += 1
            carriedWeapons.set(weapon.id, entry)
          }
          unitModels.forEach((um) => {
            um.weapon_ids.forEach((id) => {
              const weapon = weapons.find((w) => w.id === id)
              if (weapon) carry(weapon)
            })
            const enhancement = enhancements.find((e) => e.id === um.enhancement_id)
            enhancement?.weapons.forEach((w) => carry({ ...w, id: `enh-${w.id}` }))
          })
          const modelWeapons = [...carriedWeapons.values()]
          const ranged = modelWeapons.filter(({ weapon }) => weapon.weapon_type !== 'melee')
          const melee = modelWeapons.filter(({ weapon }) => weapon.weapon_type === 'melee')
          const wargearIds = [...new Set(unitModels.flatMap((um) => um.wargear_ids))]
          const modelWargear = wargear.filter((g) => wargearIds.includes(g.id))
          const abilities = model.ability_ids
            .map((id) => datasheetAbilities.find((a) => a.id === id))
            .filter(Boolean)
          return (
            <section key={modelId} className="datasheet-model">
              <h4>
                {model.name}
                {count > 1 && ` ×${count}`}
              </h4>
              <table className="datasheet-stats">
                <thead>
                  <tr>
                    <th>M</th>
                    <th>T</th>
                    <th>Sv</th>
                    <th>W</th>
                    <th>Ld</th>
                    <th>OC</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{model.movement}"</td>
                    <td>{model.toughness}</td>
                    <td>{model.save}+</td>
                    <td>{model.wounds}</td>
                    <td>{model.leadership}+</td>
                    <td>{model.oc}</td>
                  </tr>
                </tbody>
              </table>
              <p>
                {[
                  model.invulnerable &&
                    `Invulnerable save ${model.invulnerable}+` +
                      (model.invulnerable_ranged_only ? ' (ranged attacks only)' : ''),
                  model.feel_no_pain && `Feel No Pain ${model.feel_no_pain}+`,
                  model.feel_no_pain_mortal &&
                    `Feel No Pain ${model.feel_no_pain_mortal}+ vs mortal wounds`,
                  model.base_size_id !== null && `Base: ${nameOf(baseSizes, model.base_size_id)}`,
                  model.is_leader && 'Leader',
                  model.is_support && 'Support',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
              {[
                ['Ranged weapons', ranged, 'BS'],
                ['Melee weapons', melee, 'WS'],
              ].map(
                ([title, list, skill]) =>
                  list.length > 0 && (
                    <div key={title} className="datasheet-table">
                      <table>
                        <thead>
                          <tr>
                            <th>{title}</th>
                            <th>Range</th>
                            <th>A</th>
                            <th>{skill}</th>
                            <th>S</th>
                            <th>AP</th>
                            <th>D</th>
                          </tr>
                        </thead>
                        <tbody>
                          {list.map(({ weapon: w, count: carriedBy }) => (
                            <tr key={w.id}>
                              <td>
                                {w.name}
                                {carriedBy > 1 && ` ×${carriedBy}`}
                                {w.ability_ids.length > 0 && (
                                  <span className="hint">
                                    {' '}
                                    [
                                    {w.ability_ids
                                      .map((id) => nameOf(weaponAbilities, id))
                                      .join(', ')}
                                    ]
                                  </span>
                                )}
                              </td>
                              <td>{w.range !== null ? `${w.range}"` : 'Melee'}</td>
                              <td>{w.attacks}</td>
                              <td>{skillValue(w.skill)}</td>
                              <td>{w.strength}</td>
                              <td>{w.ap}</td>
                              <td>{w.damage}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
              )}
              {modelWargear.length > 0 && (
                <>
                  <h5>Wargear</h5>
                  <ul>
                    {modelWargear.map((g) => (
                      <li key={g.id}>
                        <strong>{g.name}</strong>
                        {g.description && `: ${g.description}`}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {(model.faction_ability_ids.length > 0 || abilities.length > 0) && (
                <>
                  <h5>Abilities</h5>
                  <ul>
                    {model.faction_ability_ids.length > 0 && (
                      <li>
                        <strong>Army rules:</strong>{' '}
                        {model.faction_ability_ids
                          .map((id) => nameOf(factionAbilities, id))
                          .join(', ')}
                      </li>
                    )}
                    {abilities.map((a) => (
                      <li key={a.id}>
                        <strong>{a.name}</strong>
                        {a.description && `: ${a.description}`}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {model.keyword_ids.length > 0 && (
                <p className="hint">
                  Keywords: {model.keyword_ids.map((id) => nameOf(keywords, id)).join(', ')}
                </p>
              )}
            </section>
          )
        })}
        {(carried.length > 0 || upgrade) && (
          <section className="datasheet-model">
            <h5>Enhancements</h5>
            <ul>
              {carried.map((e) => (
                <li key={e.id}>
                  <strong>{e.name}</strong>
                  {e.description && `: ${e.description}`}
                </li>
              ))}
              {upgrade && (
                <li>
                  <strong>{upgrade.name} (upgrade)</strong>
                  {upgrade.description && `: ${upgrade.description}`}
                </li>
              )}
            </ul>
          </section>
        )}
      </div>
    </CardTextAccordion>
  )
}

export default UnitDatasheet
