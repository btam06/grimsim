import { useState } from 'react'
import CardTextAccordion from './CardTextAccordion'

// The score history (see each player's scores): VP by battle round - primary
// and secondary, each capped at 15 a round - with what each score was for.
// During the game it's a collapsed table under the board; at the end of the
// game it's the final breakdown, open, with the winner.

const ROUNDS = [1, 2, 3, 4, 5]

function roundScores(player, round, kind) {
  return player.scores.filter((s) => s.battle_round === round && s.kind === kind)
}

function total(scores) {
  return scores.reduce((sum, s) => sum + s.points, 0)
}

function scoreLabel(player, score) {
  if (score.kind === 'primary') return player.primary_mission_name ?? 'Primary'
  return player.secondaries.find((c) => c.id === score.game_secondary_id)?.name ?? 'Secondary'
}

function Breakdown({ game }) {
  const [open, setOpen] = useState(null)
  return (
    <>
      <table className="score-history">
        <thead>
          <tr>
            <th>Round</th>
            {game.players.map((p) => (
              <th key={p.seat} colSpan={3}>
                {p.user_name}
              </th>
            ))}
          </tr>
          <tr>
            <th />
            {game.players.map((p) => [
              <th key={`${p.seat}-p`}>Primary</th>,
              <th key={`${p.seat}-s`}>Secondary</th>,
              <th key={`${p.seat}-t`}>Total</th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {ROUNDS.map((round) => (
            <tr
              key={round}
              className={open === round ? 'score-history-open' : undefined}
              onClick={() => setOpen(open === round ? null : round)}
              title="Show what was scored"
            >
              <td>{round}</td>
              {game.players.map((p) => {
                const primary = total(roundScores(p, round, 'primary'))
                const secondary = total(roundScores(p, round, 'secondary'))
                return [
                  <td key={`${p.seat}-p`}>{primary}</td>,
                  <td key={`${p.seat}-s`}>{secondary}</td>,
                  <td key={`${p.seat}-t`}>
                    <strong>{primary + secondary}</strong>
                  </td>,
                ]
              })}
            </tr>
          ))}
          <tr className="score-history-total">
            <td>Total</td>
            {game.players.map((p) => {
              const primary = total(p.scores.filter((s) => s.kind === 'primary'))
              const secondary = total(p.scores.filter((s) => s.kind === 'secondary'))
              return [
                <td key={`${p.seat}-p`}>{primary}</td>,
                <td key={`${p.seat}-s`}>{secondary}</td>,
                <td key={`${p.seat}-t`}>
                  <strong>{p.vp}</strong>
                </td>,
              ]
            })}
          </tr>
        </tbody>
      </table>
      {open !== null && (
        <div className="score-history-detail">
          <h4>Battle round {open}</h4>
          {game.players.map((p) => {
            const scores = p.scores.filter((s) => s.battle_round === open)
            return (
              <div key={p.seat}>
                <strong>{p.user_name}</strong>
                {scores.length === 0 ? (
                  <p className="hint">Nothing scored.</p>
                ) : (
                  <ul className="score-reasons">
                    {scores.map((s) => (
                      <li key={s.id}>
                        {scoreLabel(p, s)} — {s.points} VP
                        {s.reasons.length > 0 ? (
                          <ul className="score-reasons">
                            {s.reasons.map((r, i) => (
                              <li key={i} className="hint">
                                {r.text} ({r.points} VP)
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="hint"> (scored by hand)</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

function ScoreHistory({ game }) {
  if (game.status === 'finished') {
    const [first, second] = [...game.players].sort((a, b) => b.vp - a.vp)
    const result =
      first.vp === second.vp
        ? `A draw, ${first.vp} VP each`
        : `${first.user_name} wins, ${first.vp} VP to ${second.vp}`
    return (
      <div className="deployment-panel">
        <h3>Final scores</h3>
        <p>
          <strong>{result}.</strong>{' '}
          <span className="hint">Click a round to see what was scored.</span>
        </p>
        <Breakdown game={game} />
      </div>
    )
  }
  return (
    <CardTextAccordion label="Score history" className="turn-record">
      <p className="hint">
        VP by battle round (15 primary and 15 secondary at most a round). Click a round for
        details.
      </p>
      <Breakdown game={game} />
    </CardTextAccordion>
  )
}

export default ScoreHistory
