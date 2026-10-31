import { useState } from 'react'

// The calculator's Monte Carlo simulation (POST /combat/simulate): the
// average hits, wounds and damage over the runs as bars, each with a whisker
// of one standard deviation either side - and what the defender's points
// removed come to against the attacker's points.

const MEASURES = [
  { key: 'hits', label: 'Hits' },
  { key: 'wounds', label: 'Wounds' },
  { key: 'damage', label: 'Damage' },
]

const WIDTH = 360
const HEIGHT = 200
const PAD = { top: 20, right: 12, bottom: 28, left: 36 }
const BAR = 48

// A "nice" axis top and step for values up to `max`.
function niceScale(max) {
  if (max <= 0) return { top: 1, step: 1 }
  const rough = max / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rough)
  return { top: Math.ceil(max / step) * step, step }
}

const fmt = (n) => (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(1))

function SimulationChart({ result, attackerName, defenderName }) {
  const [hover, setHover] = useState(null)
  const [showTable, setShowTable] = useState(false)
  const bars = MEASURES.map((m) => ({ ...m, ...result[m.key] }))
  const { top, step } = niceScale(Math.max(...bars.map((b) => b.mean + b.sd)))
  const plotW = WIDTH - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const y = (v) => PAD.top + plotH - (Math.max(0, v) / top) * plotH
  const slot = plotW / bars.length
  const ticks = []
  for (let t = 0; t <= top + 1e-9; t += step) ticks.push(t)

  const removed = result.points_removed
  const perHundred = result.efficiency === null ? null : result.efficiency * 100

  return (
    <div className="simulation">
      <h4>
        Over {result.runs.toLocaleString()} runs{' '}
        <span className="hint">· average ± 1 standard deviation</span>
      </h4>
      <div className="simulation-plot">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Average per run: ${bars
            .map((b) => `${b.label} ${fmt(b.mean)} ± ${fmt(b.sd)}`)
            .join(', ')}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line
                className="simulation-grid"
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y(t)}
                y2={y(t)}
              />
              <text className="simulation-tick" x={PAD.left - 6} y={y(t)} dy="0.32em">
                {Number.isInteger(t) ? t : t.toFixed(1)}
              </text>
            </g>
          ))}
          {bars.map((b, i) => {
            const cx = PAD.left + slot * (i + 0.5)
            const barTop = y(b.mean)
            const barH = PAD.top + plotH - barTop
            const r = Math.min(4, barH / 2)
            return (
              <g
                key={b.key}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
              >
                {/* A hit target bigger than the mark. */}
                <rect
                  className="simulation-hit"
                  x={cx - slot / 2}
                  y={PAD.top}
                  width={slot}
                  height={plotH}
                />
                {barH > 0 && (
                  // Rounded at the data end only, anchored to the baseline.
                  <path
                    className="simulation-bar"
                    d={`M${cx - BAR / 2},${PAD.top + plotH}
                        V${barTop + r} Q${cx - BAR / 2},${barTop} ${cx - BAR / 2 + r},${barTop}
                        H${cx + BAR / 2 - r} Q${cx + BAR / 2},${barTop} ${cx + BAR / 2},${barTop + r}
                        V${PAD.top + plotH} Z`}
                  />
                )}
                {b.sd > 0 && (
                  <g className="simulation-whisker">
                    <line x1={cx} x2={cx} y1={y(b.mean + b.sd)} y2={y(b.mean - b.sd)} />
                    <line x1={cx - 6} x2={cx + 6} y1={y(b.mean + b.sd)} y2={y(b.mean + b.sd)} />
                    <line x1={cx - 6} x2={cx + 6} y1={y(b.mean - b.sd)} y2={y(b.mean - b.sd)} />
                  </g>
                )}
                <text
                  className="simulation-value"
                  x={cx + BAR / 2 + 4}
                  y={barTop}
                  dy="0.9em"
                >
                  {fmt(b.mean)}
                </text>
                <text className="simulation-label" x={cx} y={HEIGHT - 8}>
                  {b.label}
                </text>
              </g>
            )
          })}
          <line
            className="simulation-axis"
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
          />
        </svg>
        {hover !== null && (
          <div
            className="simulation-tooltip"
            style={{ left: `${((PAD.left + slot * (hover + 0.5)) / WIDTH) * 100}%` }}
          >
            <strong>{bars[hover].label}</strong>: {fmt(bars[hover].mean)} ±{' '}
            {fmt(bars[hover].sd)}
          </div>
        )}
      </div>

      <div className="simulation-tiles">
        <div className="simulation-tile">
          <span className="simulation-tile-value">
            {fmt(removed.mean)} <span className="hint">± {fmt(removed.sd)}</span>
          </span>
          <span className="hint">
            of {defenderName}'s {result.defender_points} pts removed per run (
            {fmt(result.damage.mean)} of its {result.defender_wounds} wounds)
          </span>
        </div>
        <div className="simulation-tile">
          <span className="simulation-tile-value">
            {perHundred === null ? '—' : fmt(perHundred)}
          </span>
          <span className="hint">
            {perHundred === null
              ? `${attackerName} has no points entered`
              : `pts removed per 100 of ${attackerName}'s ${result.attacker_points} pts`}
          </span>
        </div>
      </div>

      <button type="button" className="link-button" onClick={() => setShowTable((v) => !v)}>
        {showTable ? 'Hide table' : 'Show as table'}
      </button>
      {showTable && (
        <table className="simulation-table">
          <thead>
            <tr>
              <th>Per run</th>
              <th>Average</th>
              <th>Std. dev.</th>
            </tr>
          </thead>
          <tbody>
            {[
              ...bars,
              { label: 'Models destroyed', ...result.models_destroyed },
              { label: 'Points removed', ...removed },
            ].map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.mean.toFixed(2)}</td>
                <td>{row.sd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default SimulationChart
