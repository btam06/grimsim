import { useEffect, useState } from 'react'
import {
  deleteList,
  listDetachments,
  listEligible,
  listEnhancements,
  listFactionUnits,
  listFactions,
  listKeywords,
  listUsers,
  listLists,
  listModels,
  listUnits,
  listWargear,
  listWeapons,
} from '../api'
import ConfirmDialog from './ConfirmDialog'
import ListFormPage from './ListFormPage'
import ListsListPage from './ListsListPage'
import UnitFormPage from './UnitFormPage'

function ListsPanel() {
  const [lists, setLists] = useState([])
  // Kept here rather than on the list page, so it survives opening a form.
  const [factionFilter, setFactionFilter] = useState('')
  const [factions, setFactions] = useState([])
  const [detachments, setDetachments] = useState([])
  const [units, setUnits] = useState([])
  const [models, setModels] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [enhancements, setEnhancements] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [keywords, setKeywords] = useState([])
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [editingList, setEditingList] = useState(null)
  const [editingUnit, setEditingUnit] = useState(null)
  // The list waiting on delete confirmation, if any.
  const [pendingDelete, setPendingDelete] = useState(null)

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
    listEnhancements().then(setEnhancements).catch((err) => setError(err.message))
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
    listUsers().then(setUsers).catch((err) => setError(err.message))
  }, [])

  // The faction units and models a unit in the list being edited can use -
  // its faction's, plus any its ally rules let in (e.g. Agents of the
  // Imperium) - from the server, refreshed whenever the unit form opens.
  const [eligible, setEligible] = useState({ faction_unit_ids: [], model_ids: [] })
  useEffect(() => {
    if (view !== 'unit-form' || !editingList) return
    listEligible(editingList.id)
      .then(setEligible)
      .catch((err) => setError(err.message))
  }, [view, editingList])
  const eligibleFactionUnitsForList = factionUnits.filter((fu) =>
    eligible.faction_unit_ids.includes(fu.id)
  )
  const eligibleModelsForList = models.filter((m) => eligible.model_ids.includes(m.id))

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
    setPendingDelete(null)
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
        modelOptions={eligibleModelsForList}
        weapons={weapons}
        wargear={wargear}
        factionUnits={eligibleFactionUnitsForList}
        onSaved={goBackToListForm}
        onCancel={goBackToListForm}
      />
    )
  }

  if (view === 'list-form') {
    return (
      <ListFormPage
        editingList={editingList}
        users={users}
        factions={factions}
        detachments={detachments}
        units={units}
        models={models}
        keywords={keywords}
        weapons={weapons}
        wargear={wargear}
        factionUnits={factionUnits}
        enhancements={enhancements}
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
    <>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete list?"
        message={
          pendingDelete &&
          `"${pendingDelete.name}" will be deleted. This can't be undone.`
        }
        onConfirm={() => handleDeleteList(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />
      <ListsListPage
        lists={lists}
        factions={factions}
        factionFilter={factionFilter}
        onFactionFilterChange={setFactionFilter}
        detachments={detachments}
        error={error}
        onEdit={(list) => {
          setEditingList(list)
          setView('list-form')
        }}
        onAddNew={() => {
          setEditingList(null)
          setView('list-form')
        }}
        onDelete={(id) => setPendingDelete(lists.find((l) => l.id === id))}
      />
    </>
  )
}

export default ListsPanel
