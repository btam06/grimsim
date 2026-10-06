import { useEffect, useState } from 'react'
import AbilityPanel from './components/AbilityPanel'
import FactionsPanel from './components/FactionsPanel'
import ModelsPanel from './components/ModelsPanel'
import UnitsPanel from './components/UnitsPanel'
import WeaponsPanel from './components/WeaponsPanel'
import {
  createDatasheetAbility,
  createWeaponAbility,
  listDatasheetAbilities,
  listWeaponAbilities,
} from './api'

const TABS = ['Factions', 'Models', 'Weapons', 'Units', 'Weapon Abilities', 'Datasheet Abilities']

function App() {
  const [health, setHealth] = useState(null)
  const [tab, setTab] = useState(TABS[0])

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  return (
    <div className="app">
      <h1>Grimsim</h1>
      <p>API status: {health ? health.status : 'checking...'}</p>

      <nav className="tabs">
        {TABS.map((t) => (
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

      {tab === 'Factions' && <FactionsPanel />}
      {tab === 'Models' && <ModelsPanel />}
      {tab === 'Weapons' && <WeaponsPanel />}
      {tab === 'Units' && <UnitsPanel />}
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
    </div>
  )
}

export default App
