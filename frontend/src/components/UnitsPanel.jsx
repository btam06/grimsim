import { useEffect, useState } from 'react'
import { deleteUnit, listModels, listUnits, listWargear, listWeapons } from '../api'
import AddUnitForm from './AddUnitForm'

function UnitsPanel() {
  const [units, setUnits] = useState([])
  const [models, setModels] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [error, setError] = useState(null)

  const refresh = () => listUnits().then(setUnits).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
    listModels().then(setModels).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
    listWargear().then(setWargear).catch((err) => setError(err.message))
  }, [])

  const modelName = (id) => models.find((m) => m.id === id)?.name ?? `#${id}`
  const weaponName = (id) => weapons.find((w) => w.id === id)?.name ?? `#${id}`
  const wargearName = (id) => wargear.find((g) => g.id === id)?.name ?? `#${id}`

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deleteUnit(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Units</h2>
      {error && <p className="error">{error}</p>}
      <AddUnitForm
        listId={null}
        models={models}
        weapons={weapons}
        wargear={wargear}
        onAdded={refresh}
      />
      <ul>
        {units.map((u) => (
          <li key={u.id}>
            {u.name} — {u.points}pts —{' '}
            {u.unit_models.length === 0
              ? 'no models'
              : u.unit_models
                  .map((um) => {
                    const parts = [modelName(um.model_id)]
                    if (um.weapon_ids.length > 0) parts.push(um.weapon_ids.map(weaponName).join('/'))
                    if (um.wargear_ids.length > 0) parts.push(um.wargear_ids.map(wargearName).join('/'))
                    return parts.join(' — ')
                  })
                  .join('; ')}
            <button type="button" onClick={() => handleDelete(u.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default UnitsPanel
