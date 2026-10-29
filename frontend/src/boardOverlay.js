import { createContext, useContext, useEffect } from 'react'

// What panels want shown on the game board beyond its pieces: units being
// selected for something (highlighted - e.g. a stratagem's target, or the
// unit an ability applies to), and ranges to draw round models (e.g. Rod of
// the War Forge's 6" while it's being selected). Each panel sets its own
// entry, by key; the game view draws them all (see GameView).

// set(key, { unitIds: [...], ranges: [{ unitModelId, range, name }] })
export const BoardOverlayContext = createContext(() => {})

export function useBoardOverlay(key, { unitIds = [], ranges = [] } = {}) {
  const set = useContext(BoardOverlayContext)
  const value = JSON.stringify({ unitIds, ranges })
  useEffect(() => {
    set(key, JSON.parse(value))
    return () => set(key, null)
  }, [set, key, value])
}
