import { useEffect, useState } from 'react'
import {
  deleteList,
  listDetachments,
  listFactions,
  listLists,
  listModels,
  listUnits,
  listWargear,
  listWeapons,
} from '../api'
import ListFormPage from './ListFormPage'
import ListsListPage from './ListsListPage'
import UnitFormPage from './UnitFormPage'

function ListsPanel() {
  const [lists, setLists] = useState([])
  const [factions, setFactions] = useState([])
  const [detachments, setDetachments] = useState([])
  const [units, setUnits] = useState([])
  const [models, setModels] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingList, setEditingList] = useState(null)
  const [editingUnit, setEditingUnit] = useState(null)

  const refreshLists = () => listLists().then(setLists).catch((err) => setError(err.message))
  const refreshUnits = () => listUnits().then(setUnits).catch((err) => setError(err.message))

  useEffect(() => {
    refreshLists()
    refreshUnits()
    listFactions().then(setFactions).catch((err) => setError(err.message))
    listDetachments()
      .then(setDetachments)
      .catch((err) => setError(err.message))
    listModels().then(setModels).catch((err) => setError(err.message))
    listWeapons().then(setWeapons).catch((err) => setError(err.message))
    listWargear().then(setWargear).catch((err) => setError(err.message))
  }, [])

  const goToList = () => {
    setView('list')
    setEditingList(null)
    refreshLists()
    refreshUnits()
  }

  const goBackToListForm = () => {
    setView('list-form')
    setEditingUnit(null)
    refreshUnits()
  }

  const handleDeleteList = async (id) => {
    setError(null)
    try {
      await deleteList(id)
      refreshLists()
      refreshUnits()
    } catch (err) {
      setError(err.message)
    }
  }

  if (view === 'unit-form') {
    return (
      <UnitFormPage
        editingUnit={editingUnit}
        defaultListId={editingList?.id ?? null}
        models={models}
        weapons={weapons}
        wargear={wargear}
        lists={lists}
        onSaved={goBackToListForm}
        onCancel={goBackToListForm}
      />
    )
  }

  if (view === 'list-form') {
    return (
      <ListFormPage
        editingList={editingList}
        factions={factions}
        detachments={detachments}
        units={units}
        models={models}
        weapons={weapons}
        wargear={wargear}
        onSaved={goToList}
        onCancel={goToList}
        onUnitsChanged={refreshUnits}
        onAddUnit={() => {
          setEditingUnit(null)
          setView('unit-form')
        }}
        onEditUnit={(unit) => {
          setEditingUnit(unit)
          setView('unit-form')
        }}
      />
    )
  }

  return (
    <ListsListPage
      lists={lists}
      factions={factions}
      detachments={detachments}
      units={units}
      models={models}
      weapons={weapons}
      wargear={wargear}
      error={error}
      onEdit={(list) => {
        setEditingList(list)
        setView('list-form')
      }}
      onAddNew={() => {
        setEditingList(null)
        setView('list-form')
      }}
      onDelete={handleDeleteList}
    />
  )
}

export default ListsPanel
