import { useEffect, useMemo, useState } from 'react'
import { getDiagnosis, listDiagnoses } from '../api'

// The ML page: a diagnose run (ml/diagnose.py - a policy's games against an
// opponent, and what each side did) as charts and the full table, from
// GET /ml/diagnoses. The newest run shows first.

const SERIES = ['var(--ml-series-1)', 'var(--ml-series-2)']
const ALL = 'All lists'
const W = 600

const f1 = (n) => n.toFixed(1)
const pct = (n) => `${Math.round(n * 100)}%`
const pts = (n) => Math.round(n).toLocaleString()
const signed = (n) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}`
// (A rough text width at the charts' 11px.)
const textW = (s) => s.length * 6.2

// "ml/runs/ppo-scripted-5/model-30.pt" -> "ppo-scripted-5 / model-30";
// "app.engine.scripted:scripted" -> "scripted".
function sideName(spec, fallback) {
  if (!spec) return fallback
  if (spec.endsWith('.pt')) {
    const parts = spec.replace(/\.pt$/, '').split('/')
    return parts.slice(-2).join(' / ')
  }
  return spec.split(':').pop()
}

function Tooltip({ tip }) {
  if (!tip) return null
  return (
    <div className="ml-tip" style={{ top: `${tip.top}%` }}>
      <div className="ml-tip-title">{tip.title}</div>
      {tip.lines.map(([text, color], i) => (
        <div key={i}>
          {color && <i className="ml-swatch" style={{ background: color }} />}
          {text}
        </div>
      ))}
    </div>
  )
}

// Two bars a category, one a side: cats [{name, values: [a, b], ci?, tips?}].
function PairedBars({ cats, max, fmt, reference, names }) {
  const [hover, setHover] = useState(null)
  const bar = 9
  const band = bar * 2 + 2 + 12
  const height = cats.length * band + 24
  const labelW = Math.min(Math.max(...cats.map((c) => textW(c.name)), 40) + 12, W * 0.42)
  const right = W - 44
  // Ticks on round steps (a quarter of a rate, else 1, 2 or 5 times a power of ten).
  const rough = max / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = max === 1 ? 0.25 : [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rough)
  const top = Math.ceil(max / step - 1e-9) * step
  const ticks = []
  for (let t = 0; t <= top + 1e-9; t += step) ticks.push(t)
  const x = (v) => labelW + (Math.min(Math.max(v, 0), top) / top) * (right - labelW)
  return (
    <div className="ml-chart">
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={height - 18} className="ml-grid" />
            <text x={x(t)} y={height - 4} textAnchor="middle" className="ml-muted">
              {fmt(t)}
            </text>
          </g>
        ))}
        {reference != null && (
          <line x1={x(reference)} x2={x(reference)} y1={0} y2={height - 18} className="ml-reference" />
        )}
        {cats.map((c, i) => {
          const y0 = i * band + 4
          return (
            <g key={c.name} className={hover !== null && hover !== i ? 'ml-faded' : undefined}>
              <text x={labelW - 8} y={y0 + bar + 1} textAnchor="end" dominantBaseline="middle">
                {c.name}
              </text>
              {c.values.map((v, s) => {
                const y = y0 + s * (bar + 2)
                return (
                  <g key={s}>
                    <rect x={x(0)} y={y} width={Math.max(1, x(v) - x(0))} height={bar} rx={2} fill={SERIES[s]} />
                    {c.ci && (
                      <line x1={x(c.ci[s][0])} x2={x(c.ci[s][1])} y1={y + bar / 2} y2={y + bar / 2} className="ml-whisker" />
                    )}
                    <text x={x(v) + 4} y={y + bar / 2} dominantBaseline="middle" className="ml-muted">
                      {fmt(v)}
                    </text>
                  </g>
                )
              })}
              <rect
                x={0}
                y={y0 - 4}
                width={W}
                height={band}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          )
        })}
      </svg>
      <Tooltip
        tip={
          hover === null
            ? null
            : {
                top: ((hover * band + band) / height) * 100,
                title: cats[hover].name,
                lines: cats[hover].values.map((v, s) => [
                  `${names[s]}: ${cats[hover].tips ? cats[hover].tips[s] : fmt(v)}`,
                  SERIES[s],
                ]),
              }
        }
      />
    </div>
  )
}

const METRICS = [
  ['vp', 'VP scored', f1],
  ['primary', 'Primary VP', f1],
  ['secondary', 'Secondary VP', f1],
  ['left', 'VP left on the table', f1],
  ['shot_damage', 'Shooting damage', f1],
  ['melee_damage', 'Melee damage', f1],
  ['shot_kills', 'Models killed shooting', f1],
  ['melee_kills', 'Models killed in melee', f1],
  ['charges', 'Charges declared', f1],
  ['charges_made', 'Charges made', f1],
  ['stratagems', 'Stratagems used', f1],
  ['cp_spent', 'CP spent', f1],
  ['idle_units', 'Idle units', f1],
  ['units_lost', 'Units lost', f1],
  ['points_lost', 'Points lost', pts],
  ['discarded', 'Cards discarded', f1],
  ['achieved', 'Cards claimed', f1],
]

// Each metric on its own scale (0 to the larger value): a dot a side.
function Dumbbell({ a, b, names }) {
  const [hover, setHover] = useState(null)
  const rh = 26
  const height = METRICS.length * rh + 4
  const labelW = Math.max(...METRICS.map(([, l]) => textW(l))) + 14
  const valueW = 96
  const x0 = labelW
  const x1 = W - valueW - 8
  return (
    <div className="ml-chart">
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img">
        {METRICS.map(([k, label, fmt], i) => {
          const y = i * rh + rh / 2 + 2
          const max = Math.max(a[k], b[k]) || 1
          const x = (v) => x0 + (v / max) * (x1 - x0)
          return (
            <g key={k} className={hover !== null && hover !== i ? 'ml-faded' : undefined}>
              <text x={x0 - 10} y={y} textAnchor="end" dominantBaseline="middle">
                {label}
              </text>
              <line x1={x0} x2={x1} y1={y} y2={y} className="ml-grid" />
              <line x1={x(a[k])} x2={x(b[k])} y1={y} y2={y} className="ml-span" />
              <circle cx={x(b[k])} cy={y} r={5} fill={SERIES[1]} className="ml-dot" />
              <circle cx={x(a[k])} cy={y} r={5} fill={SERIES[0]} className="ml-dot" />
              <text x={W - 4} y={y} textAnchor="end" dominantBaseline="middle" className="ml-muted">
                {fmt(a[k])} vs {fmt(b[k])}
              </text>
              <rect
                x={0}
                y={y - rh / 2}
                width={W}
                height={rh}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          )
        })}
      </svg>
      <Tooltip
        tip={
          hover === null
            ? null
            : {
                top: (((hover + 1) * rh + 4) / height) * 100,
                title: METRICS[hover][1],
                lines: [a, b].map((r, s) => [`${names[s]}: ${METRICS[hover][2](r[METRICS[hover][0]])}`, SERIES[s]]),
              }
        }
      />
    </div>
  )
}

const COLUMNS = [
  ['list', 'List'],
  ['side', 'Side'],
  ['games', 'Games'],
  ['win', 'Win %'],
  ['vp', 'VP'],
  ['vp_against', 'VP against'],
  ['primary', 'Primary'],
  ['secondary', 'Secondary'],
  ['shot_damage', 'Shot dmg'],
  ['melee_damage', 'Melee dmg'],
  ['shot_kills', 'Shot kills'],
  ['melee_kills', 'Melee kills'],
  ['other_kills', 'Other kills'],
  ['charges', 'Charges'],
  ['charges_made', 'Made'],
  ['stratagems', 'Strats'],
  ['cp_spent', 'CP'],
  ['idle_units', 'Idle'],
  ['units_in_reserves', 'In reserves'],
  ['units_lost', 'Units lost'],
  ['units', 'Units'],
  ['left', 'VP left'],
  ['primary_left', 'Prim left'],
  ['secondary_left', 'Sec left'],
  ['capped', 'Capped'],
  ['discarded', 'Discarded'],
  ['achieved', 'Claimed'],
  ['held_unclaimed', 'Held VP'],
  ['points_left', 'Pts left'],
  ['points_lost', 'Pts lost'],
]

function cell(key, value, names) {
  if (key === 'list') return value
  if (key === 'side') return names[value === 'policy' ? 0 : 1]
  if (key === 'win') return pct(value)
  if (key === 'games') return value
  if (key.startsWith('points')) return pts(value)
  return f1(value)
}

function FullTable({ rows, names }) {
  const [sort, setSort] = useState(null)
  const sorted = useMemo(() => {
    if (!sort) return rows
    const { key, dir } = sort
    return [...rows].sort((p, q) =>
      (typeof p[key] === 'string' ? p[key].localeCompare(q[key]) : p[key] - q[key]) * dir,
    )
  }, [rows, sort])
  const click = (key) =>
    setSort((s) => ({
      key,
      dir: s && s.key === key ? -s.dir : key === 'list' || key === 'side' ? 1 : -1,
    }))
  return (
    <div className="ml-table-box">
      <table className="ml-table">
        <thead>
          <tr>
            {COLUMNS.map(([key, label]) => (
              <th
                key={key}
                aria-sort={sort?.key === key ? (sort.dir > 0 ? 'ascending' : 'descending') : undefined}
              >
                <button type="button" onClick={() => click(key)}>
                  {label}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={`${r.list}|${r.side}`} className={r.list === ALL ? 'ml-all' : undefined}>
              {COLUMNS.map(([key]) => (
                <td key={key}>{cell(key, r[key], names)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Tile({ label, value, sub }) {
  return (
    <div className="ml-tile">
      <span className="hint">{label}</span>
      <span className="ml-big">{value}</span>
      {sub && <span className="hint">{sub}</span>}
    </div>
  )
}

function Diagnosis({ data }) {
  const names = [sideName(data.policy, 'Policy'), sideName(data.opponent, 'Opponent')]
  const row = (list, side) => data.by_list.find((r) => r.list === list && r.side === side)
  const a = row(ALL, 'policy')
  const b = row(ALL, 'opponent')
  if (!a || !b) return <p className="hint">No finished games in this run.</p>
  const lists = [ALL, ...new Set(data.by_list.filter((r) => r.list !== ALL).map((r) => r.list))]
  const sides = ['policy', 'opponent']
  const perList = (fn) =>
    lists.map((list) => {
      const rs = sides.map((s) => row(list, s) ?? null)
      return { name: list, ...fn(rs.map((r) => r ?? { win: 0, win_lo: 0, win_hi: 0, games: 0, charges: 0, charges_made: 0, charge_rate: 0 })) }
    })
  const strats = (items) => items.map((s) => ({ name: s.name, values: s.values }))
  const stratMax = Math.max(0.1, ...data.stratagems.flatMap((s) => s.values), ...data.stratagem_times.flatMap((s) => s.values))
  const twoDp = (n) => (Math.round(n * 100) / 100).toString()

  return (
    <>
      <p className="ml-takeaway">
        Over <strong>{data.games}</strong> games{data.unfinished > 0 && ` (and ${data.unfinished} unfinished)`},{' '}
        {names[0]} won <strong>{pct(a.win)}</strong> against {names[1]} (95%: {pct(a.win_lo)}–{pct(a.win_hi)}), and
        scored <strong>{signed(a.margin)}</strong> VP a game more than it.
      </p>

      <div className="ml-tiles">
        <Tile label="Win rate (draws count half)" value={pct(a.win)} sub={`95%: ${pct(a.win_lo)}–${pct(a.win_hi)}`} />
        <Tile label="VP a game" value={f1(a.vp)} sub={`${names[1]}: ${f1(b.vp)}`} />
        <Tile label="Stratagems a game" value={f1(a.stratagems)} sub={`${names[1]}: ${f1(b.stratagems)}`} />
        <Tile label="Charges that connect" value={pct(a.charge_rate)} sub={`${names[1]}: ${pct(b.charge_rate)}`} />
      </div>

      <div className="ml-legend">
        {names.map((n, s) => (
          <span key={s}>
            <i className="ml-swatch" style={{ background: SERIES[s] }} />
            {n}
          </span>
        ))}
      </div>

      <section className="ml-section">
        <h3>How it plays</h3>
        <p className="hint">
          Averages a game. Each row has its own scale, from 0 to the larger of the two values.
        </p>
        <Dumbbell a={a} b={b} names={names} />
      </section>

      <section className="ml-section">
        <h3>Win rate on each list</h3>
        <p className="hint">
          How often each side won while playing that list, with its 95% interval. With only a few
          dozen games a list, most gaps here are noise.
        </p>
        <PairedBars
          names={names}
          max={1}
          fmt={pct}
          reference={0.5}
          cats={perList((rs) => ({
            values: rs.map((r) => r.win),
            ci: rs.map((r) => [r.win_lo, r.win_hi]),
            tips: rs.map((r) => `${pct(r.win)} (95%: ${pct(r.win_lo)}–${pct(r.win_hi)}), ${r.games} games`),
          }))}
        />
      </section>

      <section className="ml-section">
        <h3>Charges that connect, on each list</h3>
        <p className="hint">Charges made as a share of charges declared.</p>
        <PairedBars
          names={names}
          max={1}
          fmt={pct}
          cats={perList((rs) => ({
            values: rs.map((r) => r.charge_rate),
            tips: rs.map((r) => `${pct(r.charge_rate)}: ${f1(r.charges_made)} made of ${f1(r.charges)} declared a game`),
          }))}
        />
      </section>

      <section className="ml-section">
        <h3>Which stratagems, uses a game</h3>
        {data.stratagems.length === 0 ? (
          <p className="hint">This run didn't record stratagems by name.</p>
        ) : (
          <PairedBars names={names} max={stratMax} fmt={twoDp} cats={strats(data.stratagems)} />
        )}
      </section>

      <section className="ml-section">
        <h3>When stratagems are used, uses a game</h3>
        {data.stratagem_times.length === 0 ? (
          <p className="hint">This run didn't record when stratagems were used.</p>
        ) : (
          <PairedBars names={names} max={stratMax} fmt={twoDp} cats={strats(data.stratagem_times)} />
        )}
      </section>

      <section className="ml-section">
        <h3>Full output</h3>
        <p className="hint">
          Averages a game for each list and side. The bold rows are over every list. Click a column
          to sort.
        </p>
        <FullTable rows={data.by_list} names={names} />
      </section>
    </>
  )
}

function MlPanel() {
  const [runs, setRuns] = useState(null)
  const [name, setName] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listDiagnoses()
      .then((r) => {
        setRuns(r)
        if (r.length > 0) setName(r[0].name)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!name) return
    setData(null)
    getDiagnosis(name)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [name])

  return (
    <section className="ml-page">
      <h2>Checkpoint diagnosis</h2>
      {error && <p className="error">{error}</p>}
      {runs && runs.length === 0 && (
        <p className="hint">
          No diagnose runs yet. Run <code>python -m ml.diagnose</code> with <code>--out ml/data/diagnose-….jsonl</code>.
        </p>
      )}
      {runs && runs.length > 0 && (
        <label className="ml-run">
          <span className="hint">Run</span>
          <select value={name ?? ''} onChange={(e) => setName(e.target.value)}>
            {runs.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name} · {sideName(r.policy, '?')} vs {sideName(r.opponent, '?')} · {r.games} games ·{' '}
                {new Date(r.modified).toLocaleDateString()}
              </option>
            ))}
          </select>
        </label>
      )}
      {data && <Diagnosis data={data} />}
    </section>
  )
}

export default MlPanel
