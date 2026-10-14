import Field from './Field'
import Select from './Select'

// Narrows a list page to one faction. Only factions that have at least one of
// `items` (anything with a faction_id) are offered, plus "All factions" ('').
function FactionFilter({ factions, items, value, onChange }) {
  const presentIds = new Set(items.map((item) => item.faction_id))
  const options = [
    { id: '', name: 'All factions' },
    ...factions.filter((f) => presentIds.has(f.id)),
  ]
  return (
    <Field label="Faction">
      <Select options={options} value={value} onChange={onChange} />
    </Field>
  )
}

export default FactionFilter
