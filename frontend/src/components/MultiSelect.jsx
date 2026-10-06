function MultiSelect({ options, value, onChange }) {
  const handleChange = (e) => {
    const selected = Array.from(e.target.selectedOptions).map((option) => Number(option.value))
    onChange(selected)
  }

  return (
    <select
      multiple
      value={value.map(String)}
      onChange={handleChange}
      size={Math.min(6, Math.max(2, options.length))}
    >
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.name}
        </option>
      ))}
    </select>
  )
}

export default MultiSelect
