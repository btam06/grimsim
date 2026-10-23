// A combat calculator result (see POST /combat): each weapon's dice and what
// it did, then the totals. `showFnp` shows Feel No Pain rolls (when the
// defender has one).
const DIE_FACES = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅']
const diceFace = (roll) => DIE_FACES[roll - 1] ?? roll

function DiceRolls({ rolls }) {
  if (rolls.length === 0) return 'none'
  return rolls.map((roll, i) => (
    <span key={i} className="die-face">
      {diceFace(roll)}
    </span>
  ))
}

function CombatResults({ result, showFnp = false }) {
  return (
    <>
      <h3>Results by Weapon</h3>
      {result.weapon_results.length === 0 && <p>No weapons fired.</p>}
      <ul>
        {result.weapon_results.map((wr) => (
          <li key={wr.name}>
            {wr.name}
            <ul>
              <li>
                Attack rolls: <DiceRolls rolls={wr.attack_rolls} />
              </li>
              <li>
                Attack rerolls: <DiceRolls rolls={wr.attack_rerolls} />
              </li>
              <li>
                Wound rolls: <DiceRolls rolls={wr.wound_rolls} />
              </li>
              {wr.wound_rerolls.length > 0 && (
                <li>
                  Wound rerolls: <DiceRolls rolls={wr.wound_rerolls} />
                </li>
              )}
              <li>
                Save rolls: <DiceRolls rolls={wr.save_rolls} />
              </li>
              {/* Only for a random Damage characteristic (e.g. D6+2). */}
              {wr.damage.includes('D') && (
                <li>
                  Damage rolls ({wr.damage}): <DiceRolls rolls={wr.damage_rolls} />
                </li>
              )}
              {showFnp && (
                <li>
                  Feel no pain rolls: <DiceRolls rolls={wr.fnp_rolls} />
                </li>
              )}
              <li>Total damage dealt: {wr.total_damage}</li>
              <li>Defending models destroyed: {wr.models_destroyed}</li>
              {wr.hazardous_rolls.length > 0 && (
                <>
                  <li>
                    Hazardous rolls: <DiceRolls rolls={wr.hazardous_rolls} />
                  </li>
                  <li>Hazardous wounds taken: {wr.hazardous_wounds}</li>
                </>
              )}
            </ul>
          </li>
        ))}
      </ul>

      <h3>Overall</h3>
      <ul>
        <li>Total damage dealt: {result.total_damage}</li>
        <li>Defending models destroyed: {result.models_destroyed}</li>
        <li>Defending models remaining: {result.defending_models_remaining}</li>
        {result.hazardous_rolls.length > 0 && (
          <>
            <li>Hazardous wounds taken: {result.hazardous_wounds}</li>
            <li>Hazardous attackers destroyed: {result.hazardous_models_destroyed}</li>
          </>
        )}
        {result.deadly_demise_rolls.length > 0 && (
          <>
            <li>
              Deadly Demise rolls: <DiceRolls rolls={result.deadly_demise_rolls} />
            </li>
            <li>Deadly Demise explosions: {result.deadly_demise_explosions}</li>
          </>
        )}
      </ul>
    </>
  )
}

export default CombatResults
