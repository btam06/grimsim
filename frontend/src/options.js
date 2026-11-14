// Display options set in Debug > Options (see OptionsPanel), kept in this
// browser.

const PREFIX = 'grimsim.option.'

export const SHOW_ML_GAMES = 'showMlGames'

export function getOption(name, fallback) {
  try {
    const stored = localStorage.getItem(PREFIX + name)
    return stored === null ? fallback : JSON.parse(stored)
  } catch {
    return fallback
  }
}

export function setOption(name, value) {
  try {
    localStorage.setItem(PREFIX + name, JSON.stringify(value))
  } catch {
    // (Not kept - e.g. storage blocked.)
  }
}
