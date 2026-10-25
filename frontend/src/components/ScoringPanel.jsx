import { useEffect, useState } from 'react'
import { claimOffer, getScoring, holdOffer } from '../api'

// Automatic scoring (see app/services/in_game/scoring.py): the tactical
// secondaries completed at this scoring moment, for their holder to claim
// (scored, and the card's done) or hold (it stays in their hand, to be
// claimed later when it might be worth more) - the game waits until each is
// answered - and what's been scored automatically this turn, line by line.

function ScoringPanel({ game, onAction, onError }) {
  const [scoring, setScoring] = useState(null)

  useEffect(() => {
    if (game.status !== 'in_progress') {
      setScoring(null)
      return
    }
    let cancelled = false
    getScoring(game.id)
      .then((s) => !cancelled && setScoring(s))
      .catch((err) => onError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  if (!scoring) return null
  const nameOf = (seat) => game.players.find((p) => p.seat === seat)?.user_name
  const secondaryName = (seat, id) =>
    game.players.find((p) => p.seat === seat)?.secondaries.find((c) => c.id === id)?.name
  const scored = Object.entries(scoring.scored).flatMap(([seat, scores]) =>
    scores.filter((s) => s.reasons.length > 0).map((s) => ({ seat: Number(seat), ...s }))
  )
  if (scoring.offers.length === 0 && scored.length === 0) return null

  return (
    <div className="deployment-panel">
      <h3>Scoring</h3>
      {scoring.offers.length > 0 && (
        <>
          <p className="hint">
            Completed tactical secondaries: claim one now, or hold it to claim on a later turn
            (it&apos;s checked again then).
          </p>
          <ul className="round-start-rules">
            {scoring.offers.map((offer) => (
              <li key={offer.id}>
                <strong>{nameOf(offer.seat)}</strong>: {offer.name} — {offer.points} VP
                <ul className="score-reasons">
                  {offer.reasons.map((r, i) => (
                    <li key={i} className="hint">
                      {r.text} ({r.points} VP)
                    </li>
                  ))}
                </ul>
                <div className="inline-controls">
                  <button type="button" onClick={() => onAction(() => claimOffer(game.id, offer.id))}>
                    Claim {offer.points} VP
                  </button>
                  <button type="button" onClick={() => onAction(() => holdOffer(game.id, offer.id))}>
                    Hold
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {scored.length > 0 && (
        <>
          <h4>Scored this turn</h4>
          <ul className="round-start-rules">
            {scored.map((score) => (
              <li key={score.id}>
                <strong>{nameOf(score.seat)}</strong>:{' '}
                {score.kind === 'primary'
                  ? 'Primary'
                  : secondaryName(score.seat, score.game_secondary_id) ?? 'Secondary'}{' '}
                — {score.points} VP
                <ul className="score-reasons">
                  {score.reasons.map((r, i) => (
                    <li key={i} className="hint">
                      {r.text} ({r.points} VP)
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default ScoringPanel
