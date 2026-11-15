// Pick one of a few options, shown as clickable boxes (a radio group: the
// chosen box is highlighted). Options are { id, label }.
function ChoiceBoxes({ options, value, onChange, label }) {
  return (
    <div className="choice-boxes" role="radiogroup" aria-label={label}>
      {options.map((o) => {
        const chosen = o.id === value
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={chosen}
            className={`choice-box${chosen ? ' choice-box--chosen' : ''}`}
            onClick={() => !chosen && onChange(o.id)}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export default ChoiceBoxes
