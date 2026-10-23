import { useEffect, useState } from 'react'
import { deleteGame, listGames } from '../api'
import ConfirmDialog from './ConfirmDialog'
import GameView from './GameView'
import { DeleteButton } from './IconButtons'
import NewGamePage from './NewGamePage'

const statusLabel = (game) => {
  if (game.status === 'setup') return 'not started'
  if (game.status === 'deployment') return 'deploying'
  if (game.status === 'finished') return 'finished'
  return `battle round ${game.battle_round}`
}

function GamesPanel() {
  const [games, setGames] = useState([])
  const [view, setView] = useState('list')
  const [openGameId, setOpenGameId] = useState(null)
  const [error, setError] = useState(null)
  // The game waiting on delete confirmation, if any.
  const [pendingDelete, setPendingDelete] = useState(null)

  const refresh = () => listGames().then(setGames).catch((err) => setError(err.message))

  useEffect(() => {
    refresh()
  }, [])

  const backToList = () => {
    setView('list')
    setOpenGameId(null)
    refresh()
  }

  if (view === 'new') {
    return (
      <NewGamePage
        onCreated={(game) => {
          setOpenGameId(game.id)
          setView('game')
        }}
        onCancel={backToList}
      />
    )
  }
  if (view === 'game') {
    return <GameView gameId={openGameId} onBack={backToList} />
  }

  const handleDelete = async (id) => {
    setError(null)
    setPendingDelete(null)
    try {
      await deleteGame(id)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const matchup = (game) => game.players.map((p) => p.user_name).join(' vs ')

  return (
    <section>
      <h2>Games</h2>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete game?"
        message={
          pendingDelete && `${matchup(pendingDelete)} will be deleted. This can't be undone.`
        }
        onConfirm={() => handleDelete(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />
      {error && <p className="error">{error}</p>}
      <button type="button" onClick={() => setView('new')}>
        + New Game
      </button>
      <ul>
        {games.map((g) => (
          <li key={g.id}>
            {g.players.map((p) => `${p.user_name} (${p.list_name}) ${p.vp} VP`).join(' vs ')} —{' '}
            {statusLabel(g)}
            <button
              type="button"
              onClick={() => {
                setOpenGameId(g.id)
                setView('game')
              }}
            >
              Open
            </button>
            <DeleteButton onClick={() => setPendingDelete(g)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default GamesPanel
