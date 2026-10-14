import { useEffect, useState } from 'react'
import {
  listDatasheetAbilities,
  listFactionAbilities,
  listFactions,
  listKeywords,
  listModels,
  listWargear,
  listWargearAbilities,
  listWeaponAbilities,
  listWeapons,
} from '../api'
import ModelFormPage from './ModelFormPage'
import ModelsListPage from './ModelsListPage'
import WargearFormPage from './WargearFormPage'
import WeaponFormPage from './WeaponFormPage'

function ModelsPanel() {
  const [models, setModels] = useState([])
  const [factions, setFactions] = useState([])
  const [abilities, setAbilities] = useState([])
  const [keywords, setKeywords] = useState([])
  const [factionAbilities, setFactionAbilities] = useState([])
  const [weaponAbilities, setWeaponAbilities] = useState([])
  const [wargearAbilities, setWargearAbilities] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingModel, setEditingModel] = useState(null)
  const [editingWeapon, setEditingWeapon] = useState(null)
  const [editingWargear, setEditingWargear] = useState(null)

  const refreshModels = () => listModels().then(setModels).catch((err) => setError(err.message))
  const refreshWeapons = () => listWeapons().then(setWeapons).catch((err) => setError(err.message))
  const refreshWargear = () => listWargear().then(setWargear).catch((err) => setError(err.message))

  useEffect(() => {
    refreshModels()
    refreshWeapons()
    refreshWargear()
    listFactions().then(setFactions).catch((err) => setError(err.message))
    listDatasheetAbilities()
      .then(setAbilities)
      .catch((err) => setError(err.message))
    listKeywords()
      .then(setKeywords)
      .catch((err) => setError(err.message))
    listFactionAbilities()
      .then(setFactionAbilities)
      .catch((err) => setError(err.message))
    listWeaponAbilities()
      .then(setWeaponAbilities)
      .catch((err) => setError(err.message))
    listWargearAbilities()
      .then(setWargearAbilities)
      .catch((err) => setError(err.message))
  }, [])

  const goToList = () => {
    setView('list')
    setEditingModel(null)
    refreshModels()
    refreshWeapons()
    refreshWargear()
  }

  const stayOnForm = (model) => {
    setEditingModel(model)
    refreshModels()
    refreshWeapons()
    refreshWargear()
  }

  const goBackToModelForm = () => {
    setView('model-form')
    setEditingWeapon(null)
    refreshWeapons()
  }

  const goBackToModelFormFromWargear = () => {
    setView('model-form')
    setEditingWargear(null)
    refreshWargear()
  }

  if (view === 'wargear-form') {
    return (
      <WargearFormPage
        editingWargear={editingWargear}
        defaultModelId={editingModel?.id ?? null}
        wargearAbilities={wargearAbilities}
        onSaved={goBackToModelFormFromWargear}
        onCancel={goBackToModelFormFromWargear}
      />
    )
  }

  if (view === 'weapon-form') {
    return (
      <WeaponFormPage
        editingWeapon={editingWeapon}
        defaultModelId={editingModel?.id ?? null}
        weaponAbilities={weaponAbilities}
        onSaved={goBackToModelForm}
        onCancel={goBackToModelForm}
      />
    )
  }

  if (view === 'model-form') {
    return (
      <ModelFormPage
        editingModel={editingModel}
        factions={factions}
        abilities={abilities}
        keywords={keywords}
        factionAbilities={factionAbilities}
        weapons={weapons}
        wargear={wargear}
        onSaved={goToList}
        onSavedStay={stayOnForm}
        onCancel={goToList}
        onInventoryChanged={() => {
          refreshWeapons()
          refreshWargear()
        }}
        onAddWeapon={() => {
          setEditingWeapon(null)
          setView('weapon-form')
        }}
        onEditWeapon={(weapon) => {
          setEditingWeapon(weapon)
          setView('weapon-form')
        }}
        onAddWargear={() => {
          setEditingWargear(null)
          setView('wargear-form')
        }}
        onEditWargear={(item) => {
          setEditingWargear(item)
          setView('wargear-form')
        }}
      />
    )
  }

  return (
    <ModelsListPage
      models={models}
      abilities={abilities}
      keywords={keywords}
      factionAbilities={factionAbilities}
      weapons={weapons}
      wargear={wargear}
      error={error}
      onEdit={(model) => {
        setEditingModel(model)
        setView('model-form')
      }}
      onAddNew={() => {
        setEditingModel(null)
        setView('model-form')
      }}
    />
  )
}

export default ModelsPanel
