import { useEffect, useState } from 'react'
import AbilityPanel from './components/AbilityPanel'
import CalculatorPanel from './components/CalculatorPanel'
import DatasheetAbilitiesPanel from './components/DatasheetAbilitiesPanel'
import DetachmentsPanel from './components/DetachmentsPanel'
import FactionAbilitiesPanel from './components/FactionAbilitiesPanel'
import FactionUnitsPanel from './components/FactionUnitsPanel'
import FactionsPanel from './components/FactionsPanel'
import GamesPanel from './components/GamesPanel'
import KeywordsPanel from './components/KeywordsPanel'
import ListsPanel from './components/ListsPanel'
import { PrimaryMissions, SecondaryMissions } from './components/MissionsPanel'
import ModelsPanel from './components/ModelsPanel'
import StratagemsPanel from './components/StratagemsPanel'
import UnitsPanel from './components/UnitsPanel'
import UsersPanel from './components/UsersPanel'
import WargearAbilitiesPanel from './components/WargearAbilitiesPanel'
import WeaponAbilitiesPanel from './components/WeaponAbilitiesPanel'
import WeaponsPanel from './components/WeaponsPanel'
import { createDisposition, listDispositions } from './api'

const TAB_GROUPS = {
  Games: ['Games'],
  Build: ['Lists', 'Users'],
  Data: [
    'Models',
    'Datasheet Abilities',
    'Dispositions',
    'Factions',
    'Detachments',
    'Stratagems',
    'Secondary Missions',
    'Primary Missions',
  ],
  Debug: [
    'Weapons',
    'Units',
    'Faction Units',
    'Keywords',
    'Weapon Abilities',
    'Wargear Abilities',
    'Faction Abilities',
  ],
  Calculator: ['Calculator'],
}

const GROUPS = Object.keys(TAB_GROUPS)

function App() {
  const [health, setHealth] = useState(null)
  const [group, setGroup] = useState(GROUPS[0])
  const [tab, setTab] = useState(TAB_GROUPS[GROUPS[0]][0])

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  const handleGroupChange = (g) => {
    setGroup(g)
    setTab(TAB_GROUPS[g][0])
  }

  return (
    <div className="app">
      <h1>Grimsim</h1>
      <p>API status: {health ? health.status : 'checking...'}</p>

      <nav className="tabs">
        {GROUPS.map((g) => (
          <button
            key={g}
            type="button"
            className={g === group ? 'active' : ''}
            onClick={() => handleGroupChange(g)}
          >
            {g}
          </button>
        ))}
      </nav>

      {TAB_GROUPS[group].length > 1 && (
        <nav className="tabs subtabs">
          {TAB_GROUPS[group].map((t) => (
            <button
              key={t}
              type="button"
              className={t === tab ? 'active' : ''}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>
      )}

      {tab === 'Calculator' && <CalculatorPanel />}
      {tab === 'Games' && <GamesPanel />}
      {tab === 'Users' && <UsersPanel />}
      {tab === 'Secondary Missions' && <SecondaryMissions />}
      {tab === 'Primary Missions' && <PrimaryMissions />}
      {tab === 'Factions' && <FactionsPanel />}
      {tab === 'Faction Abilities' && <FactionAbilitiesPanel />}
      {tab === 'Detachments' && <DetachmentsPanel />}
      {tab === 'Stratagems' && <StratagemsPanel />}
      {tab === 'Models' && <ModelsPanel />}
      {tab === 'Keywords' && <KeywordsPanel />}
      {tab === 'Weapons' && <WeaponsPanel />}
      {tab === 'Units' && <UnitsPanel />}
      {tab === 'Faction Units' && <FactionUnitsPanel />}
      {tab === 'Lists' && <ListsPanel />}
      {tab === 'Weapon Abilities' && <WeaponAbilitiesPanel />}
      {tab === 'Wargear Abilities' && <WargearAbilitiesPanel />}
      {tab === 'Datasheet Abilities' && <DatasheetAbilitiesPanel />}
      {tab === 'Dispositions' && (
        <AbilityPanel title="Dispositions" listFn={listDispositions} createFn={createDisposition} />
      )}
    </div>
  )
}

export default App
