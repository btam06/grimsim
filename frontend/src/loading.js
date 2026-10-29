import { useSyncExternalStore } from 'react'

// How many things are still loading (API requests - see api.js), for the
// loading skull (see LoadingSkull).

let pending = 0
const listeners = new Set()

function notify() {
  for (const listener of listeners) listener()
}

export function begin() {
  pending += 1
  notify()
}

export function end() {
  pending = Math.max(0, pending - 1)
  notify()
}

export function useLoading() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => pending > 0
  )
}
