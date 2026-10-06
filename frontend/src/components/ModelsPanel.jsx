import { useEffect, useState } from 'react'
import { listDatasheetAbilities, listFactions, listModels, listWeaponAbilities, listWeapons } from '../api'
import ModelFormPage from './ModelFormPage'
import ModelsListPage from './ModelsListPage'

function ModelsPanel() {
  const [models, setModels] = useState([])
  const [factions, setFactions] = useState([])
  const [abilities, setAbilities] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [weapons, setWeapons] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingModel, setEditingModel] = useState(null)

  const refreshModels = () => listModels().then(setModels).catch((err) => setError(err.message))
  const refreshWeapons = () => listWeapons().then(setWeapons).catch((err) => setError(err.message))

  useEffect(() => {
    refreshModels()
    refreshWeapons()
    listFactions().then(setFactions).catch((err) => setError(err.message))
    listDatasheetAbilities()
      .then(setAbilities)
      .catch((err) => setError(err.message))
    listWeaponAbilities()
      .then(setWeaponAbilities)
      .catch((err) => setError(err.message))
  }, [])

  const goToList = () => {
    setView('list')
    setEditingModel(null)
    refreshModels()
    refreshWeapons()
  }

  if (view === 'form') {
    return (
      <ModelFormPage
        editingModel={editingModel}
        factions={factions}
        abilities={abilities}
        weapons={weapons}
        onSaved={goToList}
        onCancel={goToList}
      />
    )
  }

  return (
    <ModelsListPage
      models={models}
      abilities={abilities}
      weapons={weapons}
      weaponAbilities={weaponAbilities}
      error={error}
      onEdit={(model) => {
        setEditingModel(model)
        setView('form')
      }}
      onAddNew={() => {
        setEditingModel(null)
        setView('form')
      }}
      onWeaponAdded={() => {
        refreshModels()
        refreshWeapons()
      }}
    />
  )
}

export default ModelsPanel
