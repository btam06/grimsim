import { faCircleInfo } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import Tooltip from '@mui/material/Tooltip'

// Text followed by an info icon whose hover (or focus) tooltip holds its
// description - or just the text, if there's no description.
export function Described({ description, children }) {
  if (!description) return children
  return (
    <>
      {children}{' '}
      <Tooltip title={description} placement="top" arrow>
        <span className="described-icon" tabIndex={0} aria-label={description}>
          <FontAwesomeIcon icon={faCircleInfo} />
        </span>
      </Tooltip>
    </>
  )
}

// One radio group per faction ability with rule options (e.g. Doctrina
// Imperatives), for picking which option is active for one side - or none,
// unless its options are `required` (no "None").
export function RuleOptionPicker({ side, abilities, choices, onChange }) {
  return abilities.map((ability) => {
    const options = ability.required
      ? ability.rule_options
      : ['', ...ability.rule_options]
    return (
      <div key={ability.key} className="radio-group">
        <Described description={ability.description}>
          {side} — {ability.name}
        </Described>
        {options.map((option) => (
          <label key={option || 'none'} className="radio-option">
            <input
              type="radio"
              name={`${side}-rule-${ability.key}`}
              checked={(choices[ability.key] ?? '') === option}
              onChange={() => onChange({ ...choices, [ability.key]: option })}
            />
            <Described description={ability.option_descriptions?.[option]}>
              {option || 'None'}
            </Described>
          </label>
        ))}
      </div>
    )
  })
}
