import ReactSelect from 'react-select'

function MultiSelect({ options, value, onChange }) {
  const selectOptions = options.map((option) => ({ value: option.id, label: option.name }))
  const selected = selectOptions.filter((option) => value.includes(option.value))

  return (
    <ReactSelect
      className="select-wrapper"
      classNamePrefix="rs"
      options={selectOptions}
      value={selected}
      onChange={(selectedOptions) => onChange((selectedOptions ?? []).map((option) => option.value))}
      isMulti
    />
  )
}

export default MultiSelect
