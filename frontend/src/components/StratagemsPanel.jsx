import { useEffect, useState } from 'react'
import {
  createStratagem,
  deleteStratagem,
  listConditions,
  listDetachments,
  listEffects,
  listKeywords,
  listStratagems,
} from '../api'
import Field from './Field'
import { DeleteButton } from './IconButtons'
import MultiSelect from './MultiSelect'
import Select from './Select'

export const PHASES = [
  { id: 'command', name: 'Command' },
  { id: 'movement', name: 'Movement' },
  { id: 'shooting', name: 'Shooting' },
  { id: 'charge', name: 'Charge' },
  { id: 'fight', name: 'Fight' },
]
const TURNS = [
  { id: 'your_turn', name: 'Your turn' },
  { id: 'opponent_turn', name: "Opponent's turn" },
  { id: 'either', name: 'Either turn' },
]
// Which unit in a combat a stratagem is used on ('' means either).
const COMBAT_SIDES = [
  { id: '', name: 'Either unit' },
  { id: 'attacker', name: 'The attacking unit' },
  { id: 'defender', name: 'The unit being attacked' },
]
const timingLabel = (t) =>
  `${PHASES.find((p) => p.id === t.phase)?.name ?? t.phase} (${(
    TURNS.find((x) => x.id === t.turn)?.name ?? t.turn
  ).toLowerCase()})`

function StratagemsPanel() {
  const [stratagems, setStratagems] = useState([])
  const [detachments, setDetachments] = useState([])
  const [conditions, setConditions] = useState([])
  const [effects, setEffects] = useState([])
  const [keywords, setKeywords] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [cp, setCp] = useState('1')
  const [isCore, setIsCore] = useState(false)
  const [detachmentIds, setDetachmentIds] = useState([])
  const [conditionIds, setConditionIds] = useState([])
  const [effectIds, setEffectIds] = useState([])
  const [keywordIds, setKeywordIds] = useState([])
  const [excludedKeywordIds, setExcludedKeywordIds] = useState([])
  // Alternative keyword sets ("one SICARIAN or SKITARII MOUNTED unit"), and
  // the one being put together.
  const [keywordOptions, setKeywordOptions] = useState([])
  const [optionDraft, setOptionDraft] = useState([])
  // When it can be used in a game; empty means any time.
  const [timings, setTimings] = useState([])
  const [timingPhase, setTimingPhase] = useState('command')
  const [timingTurn, setTimingTurn] = useState('your_turn')
  const [combatSide, setCombatSide] = useState('')
  const [error, setError] = useState(null)

  const refresh = () => listStratagems().then(setStratagems).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listDetachments().then(setDetachments).catch((err) => setError(err.message))
    listConditions().then(setConditions).catch((err) => setError(err.message))
    listEffects().then(setEffects).catch((err) => setError(err.message))
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
  }, [])

  const detachmentName = (id) => detachments.find((d) => d.id === id)?.name ?? `#${id}`
  const conditionName = (id) => conditions.find((c) => c.id === id)?.name ?? `#${id}`
  const effectName = (id) => effects.find((e) => e.id === id)?.name ?? `#${id}`
  const keywordName = (id) => keywords.find((k) => k.id === id)?.name ?? `#${id}`
  // e.g. "SICARIAN or SKITARII + MOUNTED" - each option's keywords are a
  // set, so they're sorted by name.
  const optionLabel = (option) => option.map(keywordName).sort().join(' + ')
  const optionsLabel = (options) => options.map(optionLabel).join(' or ')

  const toggleId = (list, setList, id) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!isCore && detachmentIds.length === 0) {
      setError('Select at least one detachment, or mark the stratagem as core')
      return
    }
    try {
      await createStratagem({
        name,
        description: description || null,
        cp: Number(cp),
        is_core: isCore,
        detachment_ids: isCore ? [] : detachmentIds,
        condition_ids: conditionIds,
        effect_ids: effectIds,
        keyword_ids: keywordIds,
        excluded_keyword_ids: excludedKeywordIds,
        keyword_option_ids: keywordOptions,
        timings,
        combat_side: combatSide || null,
      })
      setName('')
      setDescription('')
      setCp('1')
      setIsCore(false)
      setDetachmentIds([])
      setConditionIds([])
      setEffectIds([])
      setKeywordIds([])
      setExcludedKeywordIds([])
      setKeywordOptions([])
      setOptionDraft([])
      setTimings([])
      setCombatSide('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (id) => {
    setError(null)
    try {
      await deleteStratagem(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Stratagems</h2>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Description (optional)">
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="CP">
          <input type="number" min="0" value={cp} onChange={(e) => setCp(e.target.value)} required />
        </Field>
        <label className="checkbox-field">
          <input type="checkbox" checked={isCore} onChange={(e) => setIsCore(e.target.checked)} />
          Core stratagem (usable with any detachment)
        </label>
        {!isCore && (
          <label className="field">
            Detachments
            <MultiSelect options={detachments} value={detachmentIds} onChange={setDetachmentIds} />
          </label>
        )}
        <label className="field">
          Required keywords (a model needs all of them; none means any model)
          <MultiSelect options={keywords} value={keywordIds} onChange={setKeywordIds} />
        </label>
        <div className="checkbox-group">
          Keyword options (a model needs all of one of them; none means no options)
          {keywordOptions.length > 0 && (
            <ul>
              {keywordOptions.map((option, i) => (
                <li key={i}>
                  {optionLabel(option)}
                  <DeleteButton
                    onClick={() => setKeywordOptions(keywordOptions.filter((_, j) => j !== i))}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
        <label className="field">
          Option keywords
          <MultiSelect options={keywords} value={optionDraft} onChange={setOptionDraft} />
        </label>
        <button
          type="button"
          disabled={optionDraft.length === 0}
          onClick={() => {
            setKeywordOptions([...keywordOptions, optionDraft])
            setOptionDraft([])
          }}
        >
          Add keyword option
        </button>
        <label className="field">
          Excluded keywords (a model with any of them can't be targeted)
          <MultiSelect
            options={keywords}
            value={excludedKeywordIds}
            onChange={setExcludedKeywordIds}
          />
        </label>
        <div className="checkbox-group">
          Usable in (none means any time)
          {timings.length > 0 && (
            <ul>
              {timings.map((t, i) => (
                <li key={i}>
                  {timingLabel(t)}
                  <DeleteButton onClick={() => setTimings(timings.filter((_, j) => j !== i))} />
                </li>
              ))}
            </ul>
          )}
        </div>
        <Field label="Phase">
          <Select options={PHASES} value={timingPhase} onChange={setTimingPhase} />
        </Field>
        <Field label="Turn">
          <Select options={TURNS} value={timingTurn} onChange={setTimingTurn} />
        </Field>
        <button
          type="button"
          onClick={() => {
            const exists = timings.some((t) => t.phase === timingPhase && t.turn === timingTurn)
            if (!exists) setTimings([...timings, { phase: timingPhase, turn: timingTurn }])
          }}
        >
          Add timing
        </button>
        <Field label="Used on (in combat)">
          <Select options={COMBAT_SIDES} value={combatSide} onChange={setCombatSide} />
        </Field>
        <div className="checkbox-group">
          Conditions
          <div className="checkbox-grid">
            {conditions.map((c) => (
              <label key={c.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={conditionIds.includes(c.id)}
                  onChange={() => toggleId(conditionIds, setConditionIds, c.id)}
                />
                {c.name}
              </label>
            ))}
          </div>
        </div>
        <div className="checkbox-group">
          Effects
          <div className="checkbox-grid">
            {effects.map((e) => (
              <label key={e.id} className="checkbox-field">
                <input
                  type="checkbox"
                  checked={effectIds.includes(e.id)}
                  onChange={() => toggleId(effectIds, setEffectIds, e.id)}
                />
                {e.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit">Add Stratagem</button>
      </form>
      <ul>
        {stratagems.map((s) => (
          <li key={s.id}>
            {s.name} — {s.cp} CP —{' '}
            {s.is_core ? 'Core' : s.detachment_ids.map(detachmentName).join(', ')}
            {s.description ? ` — ${s.description}` : ''}
            {s.condition_ids.length > 0 &&
              ` — Conditions: ${s.condition_ids.map(conditionName).join(', ')}`}
            {s.effect_ids.length > 0 && ` — Effects: ${s.effect_ids.map(effectName).join(', ')}`}
            {s.keyword_ids.length > 0 &&
              ` — Requires: ${s.keyword_ids.map(keywordName).join(', ')}`}
            {s.keyword_option_ids.length > 0 &&
              ` — Requires one of: ${optionsLabel(s.keyword_option_ids)}`}
            {s.excluded_keyword_ids.length > 0 &&
              ` — Excludes: ${s.excluded_keyword_ids.map(keywordName).join(', ')}`}
            {` — Usable: ${s.timings.length > 0 ? s.timings.map(timingLabel).join(', ') : 'any time'}`}
            {s.combat_side &&
              ` — Used on: ${COMBAT_SIDES.find((c) => c.id === s.combat_side).name.toLowerCase()}`}
            <button type="button" onClick={() => handleRemove(s.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default StratagemsPanel
