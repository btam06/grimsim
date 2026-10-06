import { useEffect, useState } from 'react'
import {
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

  if (view === 'form') {
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
      />
    )
  }

  return (
    <ListsListPage
      lists={lists}
      factions={factions}
      detachments={detachments}
      units={units}
      error={error}
      onEdit={(list) => {
        setEditingList(list)
        setView('form')
      }}
      onAddNew={() => {
        setEditingList(null)
        setView('form')
      }}
    />
  )
}

export default ListsPanel
