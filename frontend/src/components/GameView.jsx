import { useEffect, useRef, useState } from 'react'
import {
  achieveSecondary,
  advanceGame,
  discardSecondary,
  getGame,
  listUsableStratagems,
  scorePrimary,
  startGame,
  playGameStratagem,
} from '../api'
import CardTextAccordion from './CardTextAccordion'
import Select from './Select'
import { PHASES } from './StratagemsPanel'

const BATTLE_ROUNDS = 5
const phaseName = (id) => PHASES.find((p) => p.id === id)?.name ?? id
const completesOnLabel = (value) =>
  ({ your_turn: 'your turn', opponent_turn: "opponent's turn", either: 'either turn' })[value] ??
  value

// Picks the target Secondary Mission for a stratagem like New Orders (discard
// it and draw a new one), in a native <dialog> modal.
function ReplaceSecondaryDialog({ dialogRef, stratagem, cards, onConfirm }) {
  const [cardId, setCardId] = useState(null)

  const close = () => {
    setCardId(null)
    dialogRef.current?.close()
  }

  return (
    <dialog ref={dialogRef} className="app-dialog" onClose={() => setCardId(null)}>
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault()
          if (cardId === null) return
          onConfirm(cardId)
          close()
        }}
      >
        <h3>{stratagem?.name}</h3>
        <p>Choose a Secondary Mission to discard. You'll draw one new card in its place.</p>
        <div className="radio-group">
          {cards.map((card) => (
            <label key={card.id} className="radio-option">
              <input
                type="radio"
                name="replace-secondary"
                checked={cardId === card.id}
                onChange={() => setCardId(card.id)}
              />
              {card.name} ({card.points} VP)
            </label>
          ))}
        </div>
        <div className="inline-controls">
          <button type="submit" disabled={cardId === null}>
            Discard and draw
          </button>
          <button type="button" onClick={close}>
            Cancel
          </button>
        </div>
      </form>
    </dialog>
  )
}

function PlayerCard({ game, player, onAction }) {
  const [usable, setUsable] = useState([])
  const [stratagemId, setStratagemId] = useState('')
  const replaceDialog = useRef(null)
  const [primaryPoints, setPrimaryPoints] = useState('')
  // VP to score per secondary card; starts at the card's base VP.
  const [achievePoints, setAchievePoints] = useState({})
  const inProgress = game.status === 'in_progress'
  const isTurn = game.turn_seat === player.seat

  useEffect(() => {
    setStratagemId('')
    if (!inProgress) {
      setUsable([])
      return
    }
    listUsableStratagems(game.id, player.seat)
      .then(setUsable)
      .catch(() => setUsable([]))
    // Re-check whenever the game state changes (phase, turn, CP...).
  }, [game, player.seat, inProgress])

  const active = player.secondaries.filter((c) => c.status === 'active')
  const done = player.secondaries.filter((c) => c.status !== 'active')
  const selectedStratagem = usable.find((s) => String(s.id) === String(stratagemId))

  const spendStratagem = (targetSecondaryId = null) =>
    onAction(() =>
      playGameStratagem(game.id, {
        seat: player.seat,
        stratagem_id: Number(stratagemId),
        target_secondary_id: targetSecondaryId,
      })
    )

  return (
    <div className={`player-card${isTurn ? ' player-card--turn' : ''}`}>
      <h3>
        {player.user_name}
        {isTurn && <span className="hint"> — their turn</span>}
      </h3>
      <p className="hint">
        {player.list_name} · {game.attacker_seat === player.seat ? 'Attacker' : 'Defender'}
        {game.first_seat === player.seat ? ' · goes first' : ''} ·{' '}
        {player.secondary_mode === 'fixed' ? 'Fixed' : 'Tactical'} secondaries
      </p>
      <p className="game-totals">
        <strong>{player.cp}</strong> CP · <strong>{player.vp}</strong> VP
      </p>

      <h4>Primary</h4>
      <p>
        {player.primary_mission_name ?? 'No primary mission for these dispositions'}
        {player.disposition_name && <span className="hint"> ({player.disposition_name})</span>}
      </p>
      {player.primary_mission_description && (
        <p className="hint card-text">{player.primary_mission_description}</p>
      )}
      {inProgress && (
        <div className="inline-controls">
          <input
            type="number"
            min="0"
            value={primaryPoints}
            onChange={(e) => setPrimaryPoints(e.target.value)}
            placeholder="VP"
            aria-label="Primary VP"
          />
          <button
            type="button"
            disabled={primaryPoints === ''}
            onClick={async () => {
              await onAction(() =>
                scorePrimary(game.id, { seat: player.seat, points: Number(primaryPoints) })
              )
              setPrimaryPoints('')
            }}
          >
            Add primary VP
          </button>
        </div>
      )}

      <h4>Secondaries</h4>
      {active.length === 0 && <p className="hint">None active.</p>}
      <ul>
        {active.map((card) => (
          <li key={card.id}>
            <strong>{card.name}</strong> — {card.points} VP, completes on{' '}
            {completesOnLabel(card.completes_on)}
            {card.fixed && ' (fixed)'}
            <CardTextAccordion text={card.description} />
            {inProgress && (
              <div className="inline-controls">
                <input
                  type="number"
                  min="0"
                  value={achievePoints[card.id] ?? card.points}
                  onChange={(e) => setAchievePoints({ ...achievePoints, [card.id]: e.target.value })}
                  aria-label={`VP for ${card.name}`}
                />
                <button
                  type="button"
                  onClick={() =>
                    onAction(() =>
                      achieveSecondary(game.id, card.id, Number(achievePoints[card.id] ?? card.points))
                    )
                  }
                >
                  Achieved
                </button>
                {!card.fixed && (
                  <button
                    type="button"
                    onClick={() => onAction(() => discardSecondary(game.id, card.id))}
                  >
                    Discard
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {done.length > 0 && (
        <p className="hint">
          Done: {done.map((c) => `${c.name} (${c.status})`).join(', ')}
        </p>
      )}

      <h4>Stratagems</h4>
      {inProgress ? (
        <div className="inline-controls">
          <Select
            options={usable.map((s) => ({ id: s.id, name: `${s.name} (${s.cp} CP)` }))}
            value={stratagemId}
            onChange={setStratagemId}
            placeholder={usable.length ? 'Select stratagem' : 'None usable now'}
          />
          <button
            type="button"
            disabled={!stratagemId}
            onClick={() => {
              // Stratagems that replace a secondary need their target picked first.
              if (selectedStratagem?.game_action === 'replace_secondary') {
                replaceDialog.current.showModal()
              } else {
                spendStratagem()
              }
            }}
          >
            Use
          </button>
          <ReplaceSecondaryDialog
            dialogRef={replaceDialog}
            stratagem={selectedStratagem}
            cards={active.filter((c) => !c.fixed)}
            onConfirm={spendStratagem}
          />
        </div>
      ) : (
        <p className="hint">Available once the game starts.</p>
      )}
      {player.stratagem_uses.length > 0 && (
        <ul>
          {player.stratagem_uses.map((u) => (
            <li key={u.id} className="hint">
              {u.name} — round {u.battle_round}, {phaseName(u.phase).toLowerCase()} phase, {u.cp}{' '}
              CP
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function GameView({ gameId, onBack }) {
  const [game, setGame] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getGame(gameId)
      .then(setGame)
      .catch((err) => setError(err.message))
  }, [gameId])

  // Runs a game action and shows the updated game (or the error).
  const act = async (action) => {
    setError(null)
    try {
      setGame(await action())
    } catch (err) {
      setError(err.message)
    }
  }

  if (!game) {
    return (
      <section>
        {error && <p className="error">{error}</p>}
        <p>Loading…</p>
      </section>
    )
  }

  const turnPlayer = game.players.find((p) => p.seat === game.turn_seat)
  const isSecondTurn = game.turn_seat !== null && game.turn_seat !== game.first_seat
  let advanceLabel = 'Next phase'
  if (game.phase === 'fight') {
    if (!isSecondTurn) advanceLabel = 'End turn'
    else if (game.battle_round >= BATTLE_ROUNDS) advanceLabel = 'End game'
    else advanceLabel = 'End battle round'
  }

  return (
    <section>
      <button type="button" onClick={onBack}>
        ← All games
      </button>
      <h2>
        {game.players.map((p) => p.user_name).join(' vs ')}
      </h2>
      {error && <p className="error">{error}</p>}

      {game.status === 'setup' && (
        <button type="button" onClick={() => act(() => startGame(game.id))}>
          Start first battle round
        </button>
      )}
      {game.status === 'in_progress' && (
        <div className="game-status">
          <p>
            Battle round <strong>{game.battle_round}</strong> of {BATTLE_ROUNDS} ·{' '}
            <strong>{turnPlayer?.user_name}</strong>'s turn
          </p>
          <ol className="phase-steps">
            {PHASES.map((p) => (
              <li key={p.id} className={p.id === game.phase ? 'current' : ''}>
                {p.name}
              </li>
            ))}
          </ol>
          <button type="button" onClick={() => act(() => advanceGame(game.id))}>
            {advanceLabel}
          </button>
        </div>
      )}
      {game.status === 'finished' && (
        <p>
          <strong>Game over.</strong>{' '}
          {game.players.map((p) => `${p.user_name}: ${p.vp} VP`).join(' · ')}
        </p>
      )}

      <div className="game-players">
        {game.players.map((player) => (
          <PlayerCard key={player.id} game={game} player={player} onAction={act} />
        ))}
      </div>
    </section>
  )
}

export default GameView
