import { useEffect, useState } from 'react'
import {
  deleteList,
  listDetachments,
  listFactionUnits,
  listFactions,
  listKeywords,
  listLists,
  listModels,
  listUnits,
  listWargear,
  listWeapons,
} from '../api'
import ListFormPage from './ListFormPage'
import ListsListPage from './ListsListPage'
import UnitFormPage from './UnitFormPage'

// Allied-unit rules: if every model already in the list has IMPERIUM, units
// and models from these other Imperium-aligned factions become addable too,
// as long as they carry one of the listed keywords.
const ALLIED_FACTION_RULES = [
  { factionName: 'Imperial Agents', keywordNames: ['RETINUE', 'CHARACTER', 'REQUISITIONED'] },
  { factionName: 'Imperial Knights', keywordNames: ['TITANIC', 'ARMIGER'] },
]

function ListsPanel() {
  const [lists, setLists] = useState([])
  const [factions, setFactions] = useState([])
  const [detachments, setDetachments] = useState([])
  const [units, setUnits] = useState([])
  const [models, setModels] = useState([])
  const [weapons, setWeapons] = useState([])
  const [wargear, setWargear] = useState([])
  const [factionUnits, setFactionUnits] = useState([])
  const [keywords, setKeywords] = useState([])
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
    listFactionUnits().then(setFactionUnits).catch((err) => setError(err.message))
    listKeywords().then(setKeywords).catch((err) => setError(err.message))
  }, [])

  const keywordIdByName = (name) => keywords.find((k) => k.name === name)?.id
  const factionIdByName = (name) => factions.find((f) => f.name === name)?.id
  const modelHasKeyword = (model, name) => model.keyword_ids.includes(keywordIdByName(name))

  // Every model belonging to any unit already saved into the list currently
  // being edited - used to check the IMPERIUM-wide precondition below.
  const unitsInEditingList = editingList
    ? units.filter((u) => u.list_id === editingList.id)
    : []
  const modelIdsInEditingList = new Set(
    unitsInEditingList.flatMap((u) => u.unit_models.map((um) => um.model_id))
  )
  const modelsInEditingList = models.filter((m) => modelIdsInEditingList.has(m.id))
  // Require at least one model - an empty list hasn't earned the allied
  // picks yet, even though `[].every(...)` would otherwise vacuously pass.
  const everyModelHasImperium =
    modelsInEditingList.length > 0 &&
    modelsInEditingList.every((m) => modelHasKeyword(m, 'IMPERIUM'))

  const alliedFactionIds = everyModelHasImperium
    ? ALLIED_FACTION_RULES.map((rule) => factionIdByName(rule.factionName))
    : []

  const eligibleFactionUnitsForList = factionUnits.filter(
    (fu) => fu.faction_id === editingList?.faction_id || alliedFactionIds.includes(fu.faction_id)
  )

  const eligibleModelsForList = models.filter((m) => {
    if (m.faction_id === editingList?.faction_id) return true
    if (!everyModelHasImperium) return false
    const rule = ALLIED_FACTION_RULES.find(
      (r) => factionIdByName(r.factionName) === m.faction_id
    )
    return rule ? rule.keywordNames.some((name) => modelHasKeyword(m, name)) : false
  })

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
        factions={factions}
        detachments={detachments}
        units={units}
        models={models}
        weapons={weapons}
        wargear={wargear}
        factionUnits={factionUnits}
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
      factionUnits={factionUnits}
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
