import { useEffect, useState } from 'react'
import AbilityPanel from './components/AbilityPanel'
import CalculatorPanel from './components/CalculatorPanel'
import DetachmentsPanel from './components/DetachmentsPanel'
import FactionUnitsPanel from './components/FactionUnitsPanel'
import FactionsPanel from './components/FactionsPanel'
import ListsPanel from './components/ListsPanel'
import ModelsPanel from './components/ModelsPanel'
import UnitsPanel from './components/UnitsPanel'
import WeaponsPanel from './components/WeaponsPanel'
import {
  createDatasheetAbility,
  createDisposition,
  createWeaponAbility,
  listDatasheetAbilities,
  listDispositions,
  listWeaponAbilities,
} from './api'

const TAB_GROUPS = {
  Build: ['Lists'],
  Data: [
    'Models',
    'Datasheet Abilities',
    'Weapon Abilities',
    'Dispositions',
    'Factions',
    'Detachments',
  ],
  Debug: ['Weapons', 'Units', 'Faction Units'],
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
      {tab === 'Factions' && <FactionsPanel />}
      {tab === 'Detachments' && <DetachmentsPanel />}
      {tab === 'Models' && <ModelsPanel />}
      {tab === 'Weapons' && <WeaponsPanel />}
      {tab === 'Units' && <UnitsPanel />}
      {tab === 'Faction Units' && <FactionUnitsPanel />}
      {tab === 'Lists' && <ListsPanel />}
      {tab === 'Weapon Abilities' && (
        <AbilityPanel
          title="Weapon Abilities"
          listFn={listWeaponAbilities}
          createFn={createWeaponAbility}
        />
      )}
      {tab === 'Datasheet Abilities' && (
        <AbilityPanel
          title="Datasheet Abilities"
          listFn={listDatasheetAbilities}
          createFn={createDatasheetAbility}
        />
      )}
      {tab === 'Dispositions' && (
        <AbilityPanel title="Dispositions" listFn={listDispositions} createFn={createDisposition} />
      )}
    </div>
  )
}

export default App
