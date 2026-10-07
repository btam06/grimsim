import { useEffect, useState } from 'react'
import { deleteWeapon, listModels, listWeaponAbilities, listWeapons } from '../api'
import WeaponFormPage from './WeaponFormPage'
import WeaponsListPage from './WeaponsListPage'

function WeaponsPanel() {
  const [weapons, setWeapons] = useState([])
  const [models, setModels] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingWeapon, setEditingWeapon] = useState(null)

  const refreshWeapons = () => listWeapons().then(setWeapons).catch((err) => setError(err.message))

  useEffect(() => {
    refreshWeapons()
    listModels().then(setModels).catch((err) => setError(err.message))
    listWeaponAbilities()
      .then(setWeaponAbilities)
      .catch((err) => setError(err.message))
  }, [])

  const goToList = () => {
    setView('list')
    setEditingWeapon(null)
    refreshWeapons()
  }

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deleteWeapon(id)
      refreshWeapons()
    } catch (err) {
      setError(err.message)
    }
  }

  if (view === 'form') {
    return (
      <WeaponFormPage
        editingWeapon={editingWeapon}
        defaultModelId={editingWeapon?.model_id ?? null}
        weaponAbilities={weaponAbilities}
        onSaved={goToList}
        onCancel={goToList}
      />
    )
  }

  return (
    <WeaponsListPage
      weapons={weapons}
      models={models}
      abilities={weaponAbilities}
      error={error}
      onEdit={(weapon) => {
        setEditingWeapon(weapon)
        setView('form')
      }}
      onDelete={handleDelete}
    />
  )
}

export default WeaponsPanel
