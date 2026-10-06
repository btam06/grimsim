import { useEffect, useState } from 'react'
import { deleteUnit, listLists, listModels, listUnits, listWargear, listWeapons } from '../api'
import UnitFormPage from './UnitFormPage'
import UnitsListPage from './UnitsListPage'

function UnitsPanel() {
  const [units, setUnits] = useState([])
  const [models, setModels] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [lists, setLists] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingUnit, setEditingUnit] = useState(null)

  const refreshUnits = () => listUnits().then(setUnits).catch((err) => setError(err.message))

  useEffect(() => {
    refreshUnits()
    listModels().then(setModels).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
    listWargear().then(setWargear).catch((err) => setError(err.message))
    listLists().then(setLists).catch((err) => setError(err.message))
  }, [])

  const goToList = () => {
    setView('list')
    setEditingUnit(null)
    refreshUnits()
  }

  const handleDelete = async (id) => {
    setError(null)
    try {
      await deleteUnit(id)
      refreshUnits()
    } catch (err) {
      setError(err.message)
    }
  }

  if (view === 'form') {
    return (
      <UnitFormPage
        editingUnit={editingUnit}
        defaultListId={null}
        models={models}
        weapons={weapons}
        wargear={wargear}
        lists={lists}
        onSaved={goToList}
        onCancel={goToList}
      />
    )
  }

  return (
    <UnitsListPage
      units={units}
      models={models}
      weapons={weapons}
      wargear={wargear}
      error={error}
      onEdit={(unit) => {
        setEditingUnit(unit)
        setView('form')
      }}
      onAddNew={() => {
        setEditingUnit(null)
        setView('form')
      }}
      onDelete={handleDelete}
    />
  )
}

export default UnitsPanel
