import { useEffect, useRef, useState } from 'react'
import {
  achieveSecondary,
  advanceGame,
  checkCharge,
  checkConsolidation,
  checkDeployment,
  checkMove,
  checkPileIn,
  consolidate,
  rollAdvance,
  deployUnit,
  discardSecondary,
  finishPilingIn,
  getDeployment,
  getDeploymentFormation,
  getGame,
  getCharge,
  getFight,
  getMovement,
  getPileIn,
  getShooting,
  getShootingBubble,
  makeCharge,
  moveUnit,
  pileIn as pileInUnit,
  rollCharge,
  skipConsolidation,
  getTerrainLayout,
  listUsableStratagems,
  scorePrimary,
  startGame,
  playGameStratagem,
} from '../api'
import CardTextAccordion from './CardTextAccordion'
import ChargePanel from './ChargePanel'
import DeploymentPanel from './DeploymentPanel'
import FightPanel from './FightPanel'
import Gameboard from './Gameboard'
import MovementPanel from './MovementPanel'
import PileInPanel from './PileInPanel'
import ShootingPanel from './ShootingPanel'
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

// The unit being placed (set up, moved or charging): its models' positions
// (by unit model id), the backend's check of them, and - when moving - the
// kind of move ('charge' for a charge, with how far each model can go, its
// `allowance`, and the target; 'pile_in' likewise, with the models that
// can't move, `locked`).
const NO_DRAFT = { unitId: null, positions: null, check: null, kind: null }

// The models on the board: every deployed one, and the unit being placed
// (draft - draggable, marked where the backend's check found a problem). A
// moving unit's models also leave a ghost where they started. `focus` marks
// a shooting unit and its target.
function boardPieces(game, deployment, draft, focus = {}) {
  if (!deployment) return []
  const problems = new Set((draft.check?.models ?? []).map((m) => m.unit_model_id))
  const pieces = []
  for (const unit of deployment.units) {
    const side = unit.seat === game.attacker_seat ? 'attacker' : 'defender'
    const isDraft = unit.unit_id === draft.unitId && draft.positions !== null
    const locked = new Set(draft.locked ?? [])
    for (const model of unit.models) {
      const position = isDraft ? draft.positions[model.unit_model_id] : model.position
      if (!position) continue
      const start = model.position
      if (isDraft && draft.kind && start && (start.x !== position.x || start.y !== position.y)) {
        pieces.push({
          id: `ghost-${model.unit_model_id}`,
          x: start.x,
          y: start.y,
          rotation: start.rotation,
          rx: model.width / 2,
          ry: model.height / 2,
          side,
          ghost: true,
          title: `${model.name} started here`,
        })
      }
      pieces.push({
        id: model.unit_model_id,
        x: position.x,
        y: position.y,
        rotation: position.rotation,
        rx: model.width / 2,
        ry: model.height / 2,
        side,
        draft: isDraft && !locked.has(model.unit_model_id),
        invalid: isDraft && problems.has(model.unit_model_id),
        shooter: unit.unit_id === focus.unitId,
        target: unit.unit_id === focus.targetId,
        title:
          `${unit.name}: ${model.name} (${model.base_size ?? 'no base size'})` +
          (model.wounds_remaining < model.wounds
            ? ` - ${model.wounds_remaining} of ${model.wounds} wounds left`
            : ''),
      })
    }
  }
  return pieces
}

// How far each model of the moving unit can go: a ring around where it
// started, as far as its centre can move (M, plus its Advance roll if it's
// Advancing) - and where it is now, tethered to its start.
function moveRings(deployment, movement, draft) {
  if (!deployment || !draft.kind || draft.positions === null) return []
  const unit = deployment.units.find((u) => u.unit_id === draft.unitId)
  if (!unit) return []
  // A charge or pile-in: every model the same (none for one that can't
  // move). A move: its M, plus its Advance roll if it's Advancing.
  const locked = new Set(draft.locked ?? [])
  let allowance = (id) => (locked.has(id) ? 0 : draft.allowance)
  if (!['charge', 'pile_in', 'consolidate'].includes(draft.kind)) {
    const moving = movement?.units.find((u) => u.unit_id === draft.unitId)
    if (!moving) return []
    const extra = draft.kind === 'advance' ? (moving.advance_roll ?? 0) : 0
    const characteristic = Object.fromEntries(
      moving.models.map((m) => [m.unit_model_id, m.movement])
    )
    allowance = (id) => (characteristic[id] ?? 0) + extra
  }
  return unit.models
    .filter((m) => m.position)
    .map((m) => ({
      id: m.unit_model_id,
      x: m.position.x,
      y: m.position.y,
      r: allowance(m.unit_model_id),
      to: draft.positions[m.unit_model_id] ?? m.position,
    }))
    .filter((ring) => ring.r > 0)
}

// Where the moving unit's bases can reach: round each model's start, its
// ring plus its base - drawn together as one bubble.
function moveBubble(deployment, movement, draft) {
  const rings = moveRings(deployment, movement, draft)
  if (rings.length === 0) return null
  const unit = deployment.units.find((u) => u.unit_id === draft.unitId)
  const size = Object.fromEntries(
    unit.models.map((m) => [m.unit_model_id, Math.max(m.width, m.height) / 2])
  )
  return {
    kind: 'move',
    circles: rings.map((r) => ({ id: r.id, x: r.x, y: r.y, r: r.r + (size[r.id] ?? 0) })),
  }
}

// A point pulled back onto a ring if it's outside it.
function tethered(ring, x, y) {
  const dx = x - ring.x
  const dy = y - ring.y
  const distance = Math.hypot(dx, dy)
  if (distance <= ring.r) return { x, y }
  return { x: ring.x + (dx * ring.r) / distance, y: ring.y + (dy * ring.r) / distance }
}

function GameView({ gameId, onBack }) {
  const [game, setGame] = useState(null)
  const [layout, setLayout] = useState(null)
  const [error, setError] = useState(null)
  // Both armies' units and where they're deployed; and the unit being set up:
  // its models' positions (by unit model id, once set down) and the
  // backend's check of them.
  const [deployment, setDeployment] = useState(null)
  const [draft, setDraft] = useState(NO_DRAFT)
  const [checking, setChecking] = useState(false)
  const draftRef = useRef(draft)
  draftRef.current = draft
  const checkSeq = useRef(0)
  // runCheck, for effects declared before it.
  const runCheckRef = useRef(null)
  // In the movement phase, the units the player whose turn it is can move.
  const [movement, setMovement] = useState(null)
  const moving = game?.status === 'in_progress' && game?.phase === 'movement'

  useEffect(() => {
    if (!game || !moving) {
      setMovement(null)
      return
    }
    let cancelled = false
    getMovement(game.id)
      .then((m) => !cancelled && setMovement(m))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, moving])

  // In the shooting phase, the player whose turn it is's units; and the one
  // shooting and its target, marked on the board.
  const [shooting, setShooting] = useState(null)
  const [shootingFocus, setShootingFocus] = useState({ unitId: null, targetId: null })
  const [shots, setShots] = useState(0)
  const shootingPhase = game?.status === 'in_progress' && game?.phase === 'shooting'

  useEffect(() => {
    if (!game || !shootingPhase) {
      setShooting(null)
      return
    }
    let cancelled = false
    getShooting(game.id)
      .then((s) => !cancelled && setShooting(s))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, shootingPhase, shots])

  // Where the selected shooting unit's guns reach (see GET
  // /games/{id}/shooting/bubble).
  const [sightBubble, setSightBubble] = useState(null)
  const shootingUnit = shooting?.units.find((u) => u.unit_id === shootingFocus.unitId)
  const bubbleUnitId = shootingPhase && shootingUnit?.can_shoot ? shootingUnit.unit_id : null
  useEffect(() => {
    setSightBubble(null)
    if (bubbleUnitId === null) return
    let cancelled = false
    getShootingBubble(game.id, bubbleUnitId)
      .then((b) => !cancelled && setSightBubble(b))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game?.id, bubbleUnitId])

  // In the charge phase, the player whose turn it is's units and their
  // charges.
  const [charge, setCharge] = useState(null)
  const chargePhase = game?.status === 'in_progress' && game?.phase === 'charge'
  useEffect(() => {
    if (!game || !chargePhase) {
      setCharge(null)
      return
    }
    let cancelled = false
    getCharge(game.id)
      .then((c) => !cancelled && setCharge(c))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, chargePhase])

  // In the fight phase: whose turn it is to pile in, and their units; then
  // who picks the next unit to fight, and every unit's standing.
  const [pileIn, setPileIn] = useState(null)
  const [fightState, setFightState] = useState(null)
  const [fights, setFights] = useState(0)
  const fightPhase = game?.status === 'in_progress' && game?.phase === 'fight'
  useEffect(() => {
    if (!game || !fightPhase) {
      setPileIn(null)
      setFightState(null)
      return
    }
    let cancelled = false
    Promise.all([getPileIn(game.id), getFight(game.id)])
      .then(([p, f]) => {
        if (cancelled) return
        setPileIn(p)
        setFightState(f)
      })
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, fightPhase, fights])
  const fighting = fightPhase && fightState !== null && fightState.step !== 'pile_in'

  // The unit that's just fought, while it can consolidate: its models
  // draggable from where they are now.
  const consolidatingId = fightState?.consolidating?.unit_id ?? null
  // Which consolidation that is (the unit, and how many fights there have
  // been) - and the last one finished, so it isn't started again while the
  // fight state catches up.
  const consolidationKey =
    consolidatingId === null ? null : `${consolidatingId}-${fightState.fights.length}`
  const finishedConsolidation = useRef(null)
  useEffect(() => {
    if (consolidationKey === null || !deployment) {
      setDraft((d) => (d.kind === 'consolidate' ? NO_DRAFT : d))
      return
    }
    if (consolidationKey === finishedConsolidation.current) return
    const unit = deployment.units.find((u) => u.unit_id === consolidatingId)
    const positions = Object.fromEntries(
      (unit?.models ?? [])
        .filter((m) => m.position)
        .map((m) => [
          m.unit_model_id,
          { x: m.position.x, y: m.position.y, rotation: m.position.rotation },
        ])
    )
    checkSeq.current++
    setDraft({ unitId: consolidatingId, positions, check: null, kind: 'consolidate', allowance: 3 })
    runCheckRef.current?.(consolidatingId, positions, 'consolidate')
  }, [consolidationKey, deployment])

  // A new phase or turn: nothing's being placed, or shooting.
  const stage = game ? `${game.status}-${game.battle_round}-${game.turn_seat}-${game.phase}` : ''
  useEffect(() => {
    checkSeq.current++
    setDraft(NO_DRAFT)
    setShootingFocus({ unitId: null, targetId: null })
  }, [stage])

  useEffect(() => {
    if (!game) return
    let cancelled = false
    getDeployment(game.id)
      .then((d) => !cancelled && setDeployment(d))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  // The game's terrain, drawn on the board.
  const layoutId = game?.terrain_layout_id ?? null
  useEffect(() => {
    if (layoutId === null) {
      setLayout(null)
      return
    }
    let cancelled = false
    getTerrainLayout(layoutId)
      .then((l) => !cancelled && setLayout(l))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [layoutId])

  useEffect(() => {
    getGame(gameId)
      .then(setGame)
      .catch((err) => setError(err.message))
  }, [gameId])

  // Runs a game action and shows the updated game (or the error); whether
  // it worked.
  const act = async (action) => {
    setError(null)
    try {
      setGame(await action())
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }

  // --- deployment ---

  const asPayload = (unitId, positions) => ({
    unit_id: unitId,
    positions: Object.entries(positions).map(([id, p]) => ({ unit_model_id: Number(id), ...p })),
  })

  // Asks the backend whether the draft can be deployed - or, with a kind of
  // move, moved, or charge `targetId` - as placed (only the latest answer
  // counts).
  const runCheck = async (unitId, positions, kind = null, targetId = null) => {
    if (kind === 'charge' && targetId === null) return
    const seq = ++checkSeq.current
    setChecking(true)
    try {
      let check
      if (kind === 'consolidate') {
        check = await checkConsolidation(game.id, asPayload(unitId, positions))
      } else if (kind === 'pile_in') {
        check = await checkPileIn(game.id, asPayload(unitId, positions))
      } else if (kind === 'charge') {
        const payload = { ...asPayload(unitId, positions), target_unit_id: targetId }
        check = await checkCharge(game.id, payload)
      } else if (kind) {
        check = await checkMove(game.id, { ...asPayload(unitId, positions), kind })
      } else {
        check = await checkDeployment(game.id, asPayload(unitId, positions))
      }
      if (seq === checkSeq.current) setDraft((d) => (d.unitId === unitId ? { ...d, check } : d))
    } catch (err) {
      if (seq === checkSeq.current) setError(err.message)
    } finally {
      if (seq === checkSeq.current) setChecking(false)
    }
  }

  const setDown = async (x, y) => {
    const { unitId } = draftRef.current
    setError(null)
    try {
      const formation = await getDeploymentFormation(game.id, { unit_id: unitId, x, y })
      const positions = Object.fromEntries(
        formation.map((p) => [p.unit_model_id, { x: p.x, y: p.y, rotation: p.rotation }])
      )
      setDraft({ unitId, positions, check: null })
      runCheck(unitId, positions)
    } catch (err) {
      setError(err.message)
    }
  }

  // A dragged model follows the pointer - while moving, only as far as its
  // ring (the backend still checks the distance).
  const movePiece = (id, x, y) => {
    const ring = moveRings(deployment, movement, draftRef.current).find((r) => r.id === id)
    const to = ring ? tethered(ring, x, y) : { x, y }
    setDraft((d) => ({ ...d, positions: { ...d.positions, [id]: { ...d.positions[id], ...to } } }))
  }

  runCheckRef.current = runCheck

  const dropPiece = () => {
    const { unitId, positions, kind, targetId } = draftRef.current
    if (positions) runCheck(unitId, positions, kind, targetId ?? null)
  }

  const deployDraft = async () => {
    const { unitId, positions } = draftRef.current
    if (await act(() => deployUnit(game.id, asPayload(unitId, positions)))) setDraft(NO_DRAFT)
  }

  // --- movement ---

  // Where a unit's models are now (where a move starts).
  const startPositions = (unitId) => {
    const unit = deployment?.units.find((u) => u.unit_id === unitId)
    return Object.fromEntries(
      (unit?.models ?? [])
        .filter((m) => m.position)
        .map((m) => [
          m.unit_model_id,
          { x: m.position.x, y: m.position.y, rotation: m.position.rotation },
        ])
    )
  }

  const selectMoveUnit = (unit) => {
    checkSeq.current++
    if (unit.moved) {
      setDraft({ ...NO_DRAFT, unitId: unit.unit_id })
      return
    }
    // Within Engagement Range it Falls Back; otherwise it moves normally, or
    // Advances if it's rolled to.
    let kind = unit.advance_roll ? 'advance' : 'normal'
    if (unit.allowed_kinds.includes('fall_back')) kind = 'fall_back'
    const positions = startPositions(unit.unit_id)
    setDraft({ unitId: unit.unit_id, positions, check: null, kind })
    runCheck(unit.unit_id, positions, kind)
  }

  const chooseKind = (kind) => {
    const current = draftRef.current
    let { positions } = current
    // Going from an Advance to a Normal move shrinks each ring: models
    // beyond theirs are pulled back onto it.
    if (kind !== 'advance') {
      const rings = moveRings(deployment, movement, { ...current, kind })
      positions = Object.fromEntries(
        Object.entries(positions).map(([id, p]) => {
          const ring = rings.find((r) => r.id === Number(id))
          return [id, ring ? { ...p, ...tethered(ring, p.x, p.y) } : p]
        })
      )
    }
    setDraft((d) => ({ ...d, kind, positions, check: null }))
    runCheck(current.unitId, positions, kind)
  }

  // Ticking Advance rolls the unit's D6 the first time (the backend keeps
  // it for the phase); unticking makes it a Normal move.
  const toggleAdvance = async (unit, on) => {
    if (!on) {
      chooseKind('normal')
      return
    }
    if (!unit.advance_roll) {
      setError(null)
      try {
        setMovement(await rollAdvance(game.id, { unit_id: unit.unit_id }))
      } catch (err) {
        setError(err.message)
        return
      }
    }
    chooseKind('advance')
  }

  const resetMove = () => {
    const { unitId, kind } = draftRef.current
    const positions = startPositions(unitId)
    setDraft((d) => ({ ...d, positions, check: null }))
    runCheck(unitId, positions, kind)
  }

  const moveDraft = async () => {
    const { unitId, positions, kind } = draftRef.current
    if (await act(() => moveUnit(game.id, { ...asPayload(unitId, positions), kind }))) {
      setDraft(NO_DRAFT)
    }
  }

  // --- consolidating ---

  const resetConsolidation = () => {
    const { unitId } = draftRef.current
    const positions = startPositions(unitId)
    setDraft((d) => ({ ...d, positions, check: null }))
    runCheck(unitId, positions, 'consolidate')
  }

  const finishConsolidation = async (action) => {
    const key = consolidationKey
    checkSeq.current++
    if (await act(action)) {
      finishedConsolidation.current = key
      setDraft(NO_DRAFT)
    }
  }

  const consolidateDraft = () => {
    const { unitId, positions } = draftRef.current
    return finishConsolidation(() => consolidate(game.id, asPayload(unitId, positions)))
  }

  const skipConsolidating = () =>
    finishConsolidation(() => skipConsolidation(game.id, { unit_id: consolidatingId }))

  // --- piling in ---

  const startPileIn = (unit) => {
    checkSeq.current++
    const positions = startPositions(unit.unit_id)
    setDraft({
      unitId: unit.unit_id,
      positions,
      check: null,
      kind: 'pile_in',
      allowance: 3,
      locked: unit.locked_unit_model_ids,
    })
    runCheck(unit.unit_id, positions, 'pile_in')
  }

  const resetPileIn = () => {
    const { unitId } = draftRef.current
    const positions = startPositions(unitId)
    setDraft((d) => ({ ...d, positions, check: null }))
    runCheck(unitId, positions, 'pile_in')
  }

  const pileInDraft = async () => {
    const { unitId, positions } = draftRef.current
    if (await act(() => pileInUnit(game.id, asPayload(unitId, positions)))) setDraft(NO_DRAFT)
  }

  const donePilingIn = async (seat) => {
    if (await act(() => finishPilingIn(game.id, { seat }))) setDraft(NO_DRAFT)
  }

  // --- charging ---

  const startCharge = (unit) => {
    checkSeq.current++
    if (unit.roll === null || unit.charged || unit.failed) {
      setDraft({ ...NO_DRAFT, unitId: unit.unit_id })
      return
    }
    setDraft({
      unitId: unit.unit_id,
      positions: startPositions(unit.unit_id),
      check: null,
      kind: 'charge',
      allowance: unit.roll,
      targetId: null,
    })
  }

  const rollUnitCharge = async (unit) => {
    setError(null)
    try {
      const result = await rollCharge(game.id, { unit_id: unit.unit_id })
      setCharge(result)
      startCharge(result.units.find((u) => u.unit_id === unit.unit_id))
    } catch (err) {
      setError(err.message)
    }
  }

  const chooseChargeTarget = (targetId) => {
    const { unitId, positions } = draftRef.current
    setDraft((d) => ({ ...d, targetId, check: null }))
    runCheck(unitId, positions, 'charge', targetId)
  }

  const resetCharge = () => {
    const { unitId, targetId } = draftRef.current
    const positions = startPositions(unitId)
    setDraft((d) => ({ ...d, positions, check: null }))
    runCheck(unitId, positions, 'charge', targetId)
  }

  const chargeDraft = async () => {
    const { unitId, positions, targetId } = draftRef.current
    const payload = { ...asPayload(unitId, positions), target_unit_id: targetId }
    if (await act(() => makeCharge(game.id, payload))) setDraft(NO_DRAFT)
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
  const attacker = game.players.find((p) => p.seat === game.attacker_seat)
  const defender = game.players.find((p) => p.seat !== game.attacker_seat)
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
          {layout?.deployment ? 'Start deployment' : 'Start first battle round'}
        </button>
      )}
      {game.status === 'deployment' && (
        <DeploymentPanel
          game={game}
          deployment={deployment}
          draft={draft}
          checking={checking}
          onSelectUnit={(unitId) => {
            checkSeq.current++
            setDraft({ ...NO_DRAFT, unitId })
          }}
          onPickUp={() => {
            checkSeq.current++
            setDraft((d) => ({ ...NO_DRAFT, unitId: d.unitId }))
          }}
          onDeploy={deployDraft}
        />
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
      {moving && (
        <MovementPanel
          player={turnPlayer}
          movement={movement}
          draft={draft}
          checking={checking}
          onSelectUnit={selectMoveUnit}
          onToggleAdvance={toggleAdvance}
          onReset={resetMove}
          onMove={moveDraft}
        />
      )}
      {fighting && (
        <FightPanel
          game={game}
          fightState={fightState}
          focus={shootingFocus}
          onFocus={setShootingFocus}
          onFought={() => {
            // The game again: destroyed models are off the battlefield.
            setFights((n) => n + 1)
            getGame(game.id)
              .then(setGame)
              .catch((err) => setError(err.message))
          }}
          onError={setError}
          draft={draft}
          checking={checking}
          onConsolidate={consolidateDraft}
          onResetConsolidation={resetConsolidation}
          onSkipConsolidation={skipConsolidating}
        />
      )}
      {fightPhase && !fighting && (
        <PileInPanel
          game={game}
          pileIn={pileIn}
          draft={draft}
          checking={checking}
          onSelectUnit={startPileIn}
          onReset={resetPileIn}
          onPileIn={pileInDraft}
          onDone={donePilingIn}
        />
      )}
      {chargePhase && (
        <ChargePanel
          game={game}
          player={turnPlayer}
          charge={charge}
          draft={draft}
          checking={checking}
          onSelectUnit={startCharge}
          onRoll={rollUnitCharge}
          onTarget={chooseChargeTarget}
          onReset={resetCharge}
          onCharge={chargeDraft}
          onError={setError}
        />
      )}
      {shootingPhase && (
        <ShootingPanel
          game={game}
          player={turnPlayer}
          shooting={shooting}
          focus={shootingFocus}
          onFocus={setShootingFocus}
          onShot={() => {
            // The game again: destroyed models are off the battlefield.
            setShots((n) => n + 1)
            getGame(game.id)
              .then(setGame)
              .catch((err) => setError(err.message))
          }}
          onError={setError}
        />
      )}
      {game.status === 'finished' && (
        <p>
          <strong>Game over.</strong>{' '}
          {game.players.map((p) => `${p.user_name}: ${p.vp} VP`).join(' · ')}
        </p>
      )}

      <Gameboard
        layout={layout}
        attacker={attacker?.user_name}
        defender={defender?.user_name}
        pieces={boardPieces(
          game,
          deployment,
          draft,
          shootingPhase || fighting
            ? shootingFocus
            : chargePhase
              ? { targetId: draft.targetId }
              : {}
        )}
        rings={moveRings(deployment, movement, draft)}
        bubbles={[
          (moving || chargePhase || fightPhase) && moveBubble(deployment, movement, draft),
          sightBubble && { kind: 'shoot', regions: sightBubble.regions },
        ].filter(Boolean)}
        onBoardClick={
          game.status === 'deployment' && draft.unitId !== null && draft.positions === null
            ? setDown
            : null
        }
        onPieceMove={movePiece}
        onPieceDrop={dropPiece}
      />
      {layoutId === null && (
        <p className="hint">
          No terrain layout for {attacker?.disposition_name ?? '—'} (attacker) vs{' '}
          {defender?.disposition_name ?? '—'} (defender) yet.
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
