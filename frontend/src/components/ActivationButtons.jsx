// An activated ability's buttons (see app/services/in_game/activations.py):
// one per unit it can target, one per option it can choose - or just "Use".

function ActivationButtons({ activation, busy, onActivate }) {
  const a = activation
  return (
    <div className="inline-controls">
      {a.targets.length === 0 && a.options.length === 0 && (
        <button type="button" disabled={busy} onClick={() => onActivate(a, {})}>
          Use
        </button>
      )}
      {a.targets.map((t) => (
        <button
          key={t.unit_id}
          type="button"
          disabled={busy}
          onClick={() => onActivate(a, { target_unit_id: t.unit_id })}
        >
          {t.name}
        </button>
      ))}
      {a.options.map((o) => (
        <button key={o} type="button" disabled={busy} onClick={() => onActivate(a, { option: o })}>
          {o}
        </button>
      ))}
    </div>
  )
}

export default ActivationButtons
