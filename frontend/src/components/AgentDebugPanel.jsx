import { useEffect, useState } from 'react'
import { applyAgentAction, getAgentDecision, getAgentLog, randomAgentAction } from '../api'

// The agent interface's debug panel (see app/routers/agent.py): what the
// game is waiting on, every legal action now (applied from here as listed,
// placements at their default), random steps, and the log of actions applied
// through the interface - each marked as listed as legal or not, and whether
// it worked. Listed but refused (a mismatch) means the legal actions and the
// game disagree. Only loads while open (building the list takes a moment).

function ActionRow({ action, busy, onApply }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="agent-action">
      <button type="button" disabled={busy || !action.concrete} onClick={() => onApply(action)}>
        Apply
      </button>{' '}
      <span>
        seat {action.seat} · {action.label}
      </span>
      {!action.concrete && <span className="hint"> · needs positions (no default found)</span>}
      {action.placement && action.concrete && (
        <span className="hint"> · placement: default ({action.placement.check})</span>
      )}{' '}
      <button type="button" className="link-button" onClick={() => setOpen((o) => !o)}>
        {open ? 'hide' : 'params'}
      </button>
      {open && (
        <pre className="agent-json">
          {JSON.stringify({ type: action.type, seat: action.seat, params: action.params, placement: action.placement }, null, 1)}
        </pre>
      )}
    </li>
  )
}

function LogRow({ entry }) {
  const [open, setOpen] = useState(false)
  const status = entry.mismatch ? 'MISMATCH' : entry.ok ? 'ok' : 'refused'
  return (
    <li className={`agent-log agent-log--${entry.mismatch ? 'mismatch' : entry.ok ? 'ok' : 'refused'}`}>
      <strong>{status}</strong> · #{entry.id} · {entry.state} · seat {entry.seat} · {entry.type}
      {!entry.listed && <span className="hint"> · not listed</span>} ·{' '}
      <span className="hint">{entry.ms} ms</span>
      {entry.result && <div className="hint">→ {entry.result}</div>}
      {entry.error && <div className="agent-error">{entry.error}</div>}{' '}
      <button type="button" className="link-button" onClick={() => setOpen((o) => !o)}>
        {open ? 'hide' : 'params'}
      </button>
      {open && <pre className="agent-json">{JSON.stringify(entry.params, null, 1)}</pre>}
    </li>
  )
}

function AgentDebugPanel({ game, onChanged }) {
  const [open, setOpen] = useState(false)
  const [decision, setDecision] = useState(null)
  const [log, setLog] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [problemsOnly, setProblemsOnly] = useState(false)
  const [expanded, setExpanded] = useState({})

  const refresh = async () => {
    setError(null)
    try {
      const [d, l] = await Promise.all([getAgentDecision(game.id), getAgentLog(game.id)])
      setDecision(d)
      setLog(l)
    } catch (err) {
      setError(err.message)
    }
  }

  // Again whenever the game changes, while open.
  useEffect(() => {
    if (open) refresh()
  }, [open, game])

  const run = async (step, times = 1) => {
    setBusy(true)
    setError(null)
    try {
      for (let i = 0; i < times; i++) {
        const result = await step()
        setDecision(result.decision)
        // Stop on a problem: a mismatch, or a crash.
        if (result.log.mismatch || (!result.log.ok && !result.log.listed && times > 1)) break
      }
      setLog(await getAgentLog(game.id))
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const apply = (action) => {
    const params = { ...action.params }
    if (action.placement) params.positions = action.placement.default
    return run(() => applyAgentAction(game.id, { type: action.type, seat: action.seat, params }))
  }

  const byType = {}
  for (const a of decision?.actions ?? []) (byType[a.type] ??= []).push(a)
  const shown = problemsOnly ? log.filter((e) => !e.ok) : log
  const mismatches = log.filter((e) => e.mismatch).length

  return (
    <details className="agent-debug" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        Agent interface (debug)
        {mismatches > 0 && <span className="agent-error"> · {mismatches} mismatches</span>}
      </summary>
      {error && <p className="error">{error}</p>}
      <div className="inline-controls">
        <button type="button" disabled={busy} onClick={refresh}>
          Refresh
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => randomAgentAction(game.id))}>
          Random step
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => run(() => randomAgentAction(game.id), 10)}
        >
          10 random steps
        </button>
        {busy && <span className="hint">Working…</span>}
      </div>
      {decision && (
        <>
          <p>
            <strong>{decision.state}</strong> · waiting for{' '}
            <strong>
              {decision.waiting_for.seat === null ? 'no one' : `seat ${decision.waiting_for.seat}`}
            </strong>{' '}
            ({decision.waiting_for.reason}) ·{' '}
            <span className="hint">
              {decision.actions.length} legal actions, listed in {decision.ms} ms
            </span>
          </p>
          <ul className="agent-types">
            {Object.entries(byType).map(([type, actions]) => (
              <li key={type}>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setExpanded((e) => ({ ...e, [type]: !e[type] }))}
                >
                  {expanded[type] ? '▾' : '▸'} {type}
                </button>{' '}
                <span className="hint">
                  × {actions.length}
                  {actions.some((a) => !a.concrete) &&
                    ` (${actions.filter((a) => !a.concrete).length} without a default placement)`}
                </span>
                {expanded[type] && (
                  <ul>
                    {actions.map((a, i) => (
                      <ActionRow key={i} action={a} busy={busy} onApply={apply} />
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <h4>
        Log{' '}
        <label className="hint">
          <input
            type="checkbox"
            checked={problemsOnly}
            onChange={(e) => setProblemsOnly(e.target.checked)}
          />{' '}
          refused and mismatches only
        </label>
      </h4>
      {shown.length === 0 && <p className="hint">Nothing applied through the interface yet.</p>}
      <ul className="agent-log-list">
        {shown.map((entry) => (
          <LogRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </details>
  )
}

export default AgentDebugPanel
