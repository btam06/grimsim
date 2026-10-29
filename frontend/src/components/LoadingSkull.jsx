import { faSkull } from '@fortawesome/free-solid-svg-icons'
import { useEffect, useState } from 'react'
import { useLoading } from '../loading'

// A spinning skull in the top left while anything's loading - shown only
// once it's taken a moment, so quick requests don't make it flicker. (While
// the app itself loads, index.html shows the same one.)

const DELAY_MS = 150
const [WIDTH, HEIGHT, , , PATH] = faSkull.icon

function LoadingSkull() {
  const loading = useLoading()
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!loading) {
      setShown(false)
      return
    }
    const timer = setTimeout(() => setShown(true), DELAY_MS)
    return () => clearTimeout(timer)
  }, [loading])
  if (!shown) return null
  return (
    <svg
      className="loading-skull"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="status"
      aria-label="Loading"
    >
      <path d={Array.isArray(PATH) ? PATH.join(' ') : PATH} />
    </svg>
  )
}

export default LoadingSkull
