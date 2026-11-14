import { useState } from 'react'
import { SHOW_ML_GAMES, getOption, setOption } from '../options'

// Debug options: whether the games list shows games made for machine
// learning (e.g. by scripts/spread_games.py).

function OptionsPanel() {
  const [showMl, setShowMl] = useState(() => getOption(SHOW_ML_GAMES, false))

  const changeShowMl = (value) => {
    setShowMl(value)
    setOption(SHOW_ML_GAMES, value)
  }

  return (
    <section>
      <h2>Options</h2>
      <label className="radio-option">
        <input type="checkbox" checked={showMl} onChange={(e) => changeShowMl(e.target.checked)} />
        Show ML games in the games list
      </label>
    </section>
  )
}

export default OptionsPanel
