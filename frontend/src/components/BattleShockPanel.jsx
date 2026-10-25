import { useState } from 'react'
import { requireBattleShockTest, takeBattleShockTest } from '../api'
import CardTextAccordion from './CardTextAccordion'
import Select from './Select'

// Battle-shock (see app/services/in_game/battle_shock.py): the tests waiting
// to be taken - each player rolls their own units' 2D6 against the unit's
// best Leadership, or uses Insane Bravery (once per battle) to pass it - the
// tests taken this phase, and the Battle-shocked units (0 OC). A rule or
// stratagem that makes a unit test (e.g. Extinction Order) can be applied
// here too.

function reasonText(reason) {
  return reason === 'battle_shock_step' ? 'Battle-shock step' : reason
}

function testLine(test) {
  return `${test.unit_name} · ${reasonText(test.reason)} · needs ${test.leadership}+${
    test.modifier ? ` (${test.modifier > 0 ? '+' : ''}${test.modifier} to the roll)` : ''
  } · strength ${test.current_strength}/${test.starting_strength}`
}

function BattleShockPanel({ game, battleShock, deployment, onChange, onError }) {
  const [unitId, setUnitId] = useState('')
  const [reason, setReason] = useState('')
  const [modifier, setModifier] = useState('0')
  const [busy, setBusy] = useState(false)

  if (!battleShock) return null
  const { pending, taken, battle_shocked: shocked } = battleShock
  const nameOf = (seat) => game.players.find((p) => p.seat === seat)?.user_name

  const run = async (action) => {
    setBusy(true)
    onError(null)
    try {
      onChange(await action())
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const candidates = (deployment?.units ?? []).filter((u) => u.deployed && !u.battle_shocked)

  return (
    <div className="deployment-panel">
      <h3>Battle-shock</h3>
      {pending.length > 0 && (
        <>
          <p className="hint">
            Roll 2D6 for each: passed on at least the unit&apos;s Leadership. The game moves on
            once every test is taken.
          </p>
          <ul className="round-start-rules">
            {pending.map((test) => {
              const bravery = battleShock.insane_bravery[test.seat]
              return (
                <li key={test.id}>
                  <strong>{nameOf(test.seat)}</strong>: {testLine(test)}
                  <div className="inline-controls">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => run(() => takeBattleShockTest(game.id, test.id, false))}
                    >
                      Roll 2D6
                    </button>
                    <button
                      type="button"
                      disabled={busy || bravery !== null}
                      title={bravery ?? undefined}
                      onClick={() => run(() => takeBattleShockTest(game.id, test.id, true))}
                    >
                      Insane Bravery ({battleShock.insane_bravery_cp ?? 1}CP)
                    </button>
                  </div>
                  {bravery && <p className="hint">Insane Bravery: {bravery}.</p>}
                </li>
              )
            })}
          </ul>
        </>
      )}
      {taken.length > 0 && (
        <ul className="round-start-rules">
          {taken.map((test) => (
            <li key={test.id}>
              {testLine(test)}:{' '}
              {test.insane_bravery
                ? 'passed with Insane Bravery'
                : `rolled ${test.dice.join(' + ')}${
                    test.modifier ? ` ${test.modifier > 0 ? '+' : '-'} ${Math.abs(test.modifier)}` : ''
                  }`}{' '}
              <strong className={test.passed ? 'deployment-ready' : 'battle-shock-failed'}>
                {test.passed ? 'Passed' : 'Failed: Battle-shocked'}
              </strong>
              {test.mortal_wounds && <span className="hint"> · {test.mortal_wounds}</span>}
            </li>
          ))}
        </ul>
      )}
      {shocked.length > 0 ? (
        <p>
          <strong>Battle-shocked</strong> (0 OC):{' '}
          {shocked.map((u) => `${u.name} (${nameOf(u.seat)})`).join(', ')}
        </p>
      ) : (
        pending.length === 0 && <p className="hint">No units are Battle-shocked.</p>
      )}
      <CardTextAccordion label="A rule or stratagem makes a unit test">
        <div className="battle-shock-require">
          <Select
            options={candidates.map((u) => ({ id: u.unit_id, name: `${u.name} (${nameOf(u.seat)})` }))}
            value={unitId}
            onChange={setUnitId}
            placeholder="Unit"
          />
          <input
            type="text"
            placeholder="Rule or stratagem (e.g. Extinction Order)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <label>
            Modifier{' '}
            <input
              type="number"
              value={modifier}
              onChange={(e) => setModifier(e.target.value)}
              className="battle-shock-modifier"
            />
          </label>
          <button
            type="button"
            disabled={busy || !unitId || !reason.trim()}
            onClick={() =>
              run(async () => {
                const result = await requireBattleShockTest(game.id, {
                  unit_id: Number(unitId),
                  reason: reason.trim(),
                  modifier: Number(modifier) || 0,
                })
                setUnitId('')
                setReason('')
                setModifier('0')
                return result
              })
            }
          >
            Add test
          </button>
        </div>
      </CardTextAccordion>
    </div>
  )
}

export default BattleShockPanel
