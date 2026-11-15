import ReactSelect from 'react-select'

const toOption = (o) => ({
  value: String(o.id),
  label: o.name,
  isDisabled: Boolean(o.disabled),
})

function Select({ options, value, onChange, placeholder, isDisabled }) {
  // (An option with `disabled` is shown but can't be picked. Options can be
  // grouped: { label, options: [...] } shows its options under a heading.)
  const selectOptions = options.map((o) =>
    o.options ? { label: o.label, options: o.options.map(toOption) } : toOption(o)
  )
  const selected =
    selectOptions.flatMap((o) => o.options ?? [o]).find((o) => o.value === value) ?? null

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
