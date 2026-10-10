import ReactSelect from 'react-select'

function Select({ options, value, onChange, placeholder, isDisabled }) {
  const selectOptions = options.map((o) => ({ value: String(o.id), label: o.name }))
  const selected = selectOptions.find((o) => o.value === value) ?? null

  return (
    <ReactSelect
      className="select-wrapper"
      classNamePrefix="rs"
      options={selectOptions}
      value={selected}
      onChange={(option) => onChange(option ? option.value : '')}
      placeholder={placeholder}
      isDisabled={isDisabled}
    />
  )
}

export default Select
