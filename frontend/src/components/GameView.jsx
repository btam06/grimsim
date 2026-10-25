import { useEffect, useRef, useState } from 'react'
import {
  achieveSecondary,
  advanceGame,
  bringIn,
  checkArrival,
  checkDisembark,
  disembark,
  getDisembarkFormation,
  getEmbarked,
  checkCharge,
  checkConsolidation,
  checkDeployment,
  checkMove,
  checkPileIn,
  consolidate,
  rollAdvance,
  declareFormations,
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
  getBattleShock,
  getMissionState,
  getOverwatch,
  getReanimation,
  checkReanimation,
  placeReanimated,
  getReserves,
  getReservesFormation,
  getReach,
  getShooting,
  getShootingBubble,
  makeCharge,
  moveUnit,
  resetMove as resetMoveApi,
  pileIn as pileInUnit,
  rollCharge,
  skipConsolidation,
  getTerrainLayout,
  listUsableStratagems,
  scorePrimary,
  startGame,
  playGameStratagem,
} from '../api'
import { basesOverlap, freeSpot, slide } from '../collision'
import CardTextAccordion from './CardTextAccordion'
import ChargePanel from './ChargePanel'
import DeploymentPanel from './DeploymentPanel'
import FightPanel from './FightPanel'
import FormationsPanel from './FormationsPanel'
import Gameboard from './Gameboard'
import MovementPanel from './MovementPanel'
import PileInPanel from './PileInPanel'
import BattleShockPanel from './BattleShockPanel'
import CommandPanel from './CommandPanel'
import MissionPanel from './MissionPanel'
import ReanimationPanel from './ReanimationPanel'
import ReservesPanel from './ReservesPanel'
import EmbarkedPanel from './EmbarkedPanel'
import RoundStartPanel from './RoundStartPanel'
import ScoringPanel from './ScoringPanel'
import ShootingPanel from './ShootingPanel'
import TurnRecord from './TurnRecord'
import ScoreHistory from './ScoreHistory'
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
      {player.primary_automatic && (
        <p className="hint">
          Scored automatically.
          {player.primary_manual && ` By hand: ${player.primary_manual}.`}
        </p>
      )}
      {inProgress && (!player.primary_automatic || player.primary_manual) && (
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
            {card.automatic && (
              <p className="hint">
                {card.fixed
                  ? 'Scored automatically.'
                  : "Offered to claim (or hold) whenever it's completed."}
              </p>
            )}
            {card.manual && <p className="hint">Scored by hand: {card.manual}.</p>}
            {inProgress && !card.automatic && (
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
                    title="At the end of your turn: +1 CP"
                    onClick={() => onAction(() => discardSecondary(game.id, card.id))}
                  >
                    Discard (+1 CP)
                  </button>
                )}
              </div>
            )}
            {inProgress && card.automatic && !card.fixed && (
              <div className="inline-controls">
                <button
                  type="button"
                  title="At the end of your turn: +1 CP"
                  onClick={() => onAction(() => discardSecondary(game.id, card.id))}
                >
                  Discard (+1 CP)
                </button>
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
// The kinds of move made in the movement phase.
const MOVE_KINDS = ['normal', 'advance', 'fall_back']

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
      // A draft can be just some of the unit's models (e.g. reanimated ones):
      // the rest stay where they are.
      const draftPosition = isDraft ? draft.positions[model.unit_model_id] : undefined
      const position = draftPosition ?? model.position
      if (!position) continue
      // Where it started: the start of the phase, when moving (`starts`).
      const start = (isDraft && draft.starts?.[model.unit_model_id]) || model.position
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
        unitId: unit.unit_id,
        x: position.x,
        y: position.y,
        rotation: position.rotation,
        rx: model.width / 2,
        ry: model.height / 2,
        side,
        draft: draftPosition !== undefined && !locked.has(model.unit_model_id),
        invalid: isDraft && problems.has(model.unit_model_id),
        shooter: unit.unit_id === focus.unitId,
        shocked: unit.battle_shocked,
        target: unit.unit_id === focus.targetId,
        title:
          `${unit.name}: ${model.name} (${model.base_size ?? 'no base size'})` +
          (model.wounds_remaining < model.wounds
            ? ` - ${model.wounds_remaining} of ${model.wounds} wounds left`
            : '') +
          (unit.battle_shocked ? ' - Battle-shocked' : ''),
      })
    }
  }
  return pieces
}

// Who controls each objective (see the deployment's `objectives`), by the
// terrain areas it is: the controller's side (none in a tie) and each
// player's OC there, for the board to shade and show.
function objectiveControl(game, deployment) {
  const found = {}
  for (const objective of deployment?.objectives ?? []) {
    const side =
      objective.controller === null
        ? null
        : objective.controller === game.attacker_seat
          ? 'attacker'
          : 'defender'
    const oc = game.players
      .map((p) => `${p.user_name} OC ${objective.oc[p.seat] ?? 0}`)
      .join(' · ')
    const holder = game.players.find((p) => p.seat === objective.controller)
    const title = `${holder ? `Controlled by ${holder.user_name}` : 'Not controlled'} (${oc})`
    for (const id of objective.area_ids) found[id] = { side, title }
  }
  return found
}

// How far the auras of the unit being moved (or placed) reach from its
// models where they are now (see the deployment's `auras`): one colour per
// aura name.
function auraCircles(deployment, draft) {
  if (!deployment || draft.positions === null || draft.unitId === null) return []
  const unit = deployment.units.find((u) => u.unit_id === draft.unitId)
  if (!unit?.auras?.length) return []
  const names = [...new Set(unit.auras.map((a) => a.name))]
  return unit.auras.flatMap((aura) => {
    const model = unit.models.find((m) => m.unit_model_id === aura.unit_model_id)
    const position = draft.positions[aura.unit_model_id] ?? model?.position
    if (!model || !position) return []
    return [
      {
        id: `${aura.unit_model_id}-${aura.name}`,
        x: position.x,
        y: position.y,
        rotation: position.rotation,
        rx: model.width / 2,
        ry: model.height / 2,
        range: aura.range,
        name: aura.name,
        colour: names.indexOf(aura.name) % 3,
      },
    ]
  })
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
      x: (draft.starts?.[m.unit_model_id] ?? m.position).x,
      y: (draft.starts?.[m.unit_model_id] ?? m.position).y,
      r: allowance(m.unit_model_id),
      to: draft.positions[m.unit_model_id] ?? m.position,
      path: wayRound(draft, m.unit_model_id),
    }))
    .filter((ring) => ring.r > 0)
}

// The way a model went round walls, per the latest check - if it ends where
// the model is now (not mid-drag since).
function wayRound(draft, id) {
  const path = draft.check?.paths?.find((p) => p.unit_model_id === id)?.points
  const at = draft.positions?.[id]
  if (!path || !at) return null
  const last = path[path.length - 1]
  return Math.abs(last.x - at.x) < 1e-3 && Math.abs(last.y - at.y) < 1e-3 ? path : null
}

// Where the moving unit's bases can reach: round each model's start, its
// ring plus its base - drawn together as one bubble.
// `reach` is the backend's areas each model can get to round walls (see POST
// /games/{id}/reach), for these rings - until it comes, plain circles.
function moveBubble(deployment, movement, draft, reach = null) {
  const rings = moveRings(deployment, movement, draft)
  if (rings.length === 0) return null
  if (reach && reach.key === reachKey(draft.unitId, rings)) {
    return {
      kind: 'move',
      regions: reach.models.flatMap((m) =>
        m.regions.map((points) => ({ points, inflate: m.clearance }))
      ),
    }
  }
  const unit = deployment.units.find((u) => u.unit_id === draft.unitId)
  const size = Object.fromEntries(
    unit.models.map((m) => [m.unit_model_id, Math.max(m.width, m.height) / 2])
  )
  return {
    kind: 'move',
    circles: rings.map((r) => ({ id: r.id, x: r.x, y: r.y, r: r.r + (size[r.id] ?? 0) })),
  }
}

// What a reach is for: the unit, and each model's start and distance.
function reachKey(unitId, rings) {
  return JSON.stringify([unitId, rings.map((r) => [r.id, r.x, r.y, r.r])])
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

  // Missions' operation markers, marked units, and the choices they're
  // waiting for (see GET /games/{id}/mission).
  const [mission, setMission] = useState(null)
  useEffect(() => {
    if (!game || game.status !== 'in_progress') {
      setMission(null)
      return
    }
    let cancelled = false
    getMissionState(game.id)
      .then((m) => !cancelled && setMission(m))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, deployment])

  // Battle-shock: tests to take, and Battle-shocked units (see GET
  // /games/{id}/battle-shock).
  const [battleShock, setBattleShock] = useState(null)
  useEffect(() => {
    if (!game || game.status !== 'in_progress') {
      setBattleShock(null)
      return
    }
    let cancelled = false
    getBattleShock(game.id)
      .then((b) => !cancelled && setBattleShock(b))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game])

  // In the command phase: Reanimation Protocols at its end, and any returned
  // models to set up (see GET /games/{id}/reanimation).
  const commandPhase = game?.status === 'in_progress' && game?.phase === 'command'
  const [reanimation, setReanimation] = useState(null)
  useEffect(() => {
    if (!game || !commandPhase) {
      setReanimation(null)
      return
    }
    let cancelled = false
    getReanimation(game.id)
      .then((r) => !cancelled && setReanimation(r))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, commandPhase])

  // In the movement phase: who can bring units in from Reserves, and which
  // (see GET /games/{id}/reserves).
  const [reserves, setReserves] = useState(null)
  useEffect(() => {
    if (!game || !moving) {
      setReserves(null)
      return
    }
    let cancelled = false
    getReserves(game.id)
      .then((r) => !cancelled && setReserves(r))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, moving])
  // The end of the movement phase: only the opponent's Rapid Ingress and
  // Fire Overwatch now.
  const endOfMovement = moving && reserves?.step === 'rapid_ingress'

  // In the movement phase: units that can disembark from their transports
  // (see GET /games/{id}/embarked).
  const [embarked, setEmbarked] = useState(null)
  useEffect(() => {
    if (!game || !moving) {
      setEmbarked(null)
      return
    }
    let cancelled = false
    getEmbarked(game.id)
      .then((e) => !cancelled && setEmbarked(e))
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

  // At the end of the movement phase: whether the opponent can Fire
  // Overwatch, and with what (see GET /games/{id}/overwatch).
  const [overwatch, setOverwatch] = useState(null)
  useEffect(() => {
    if (!game || !endOfMovement) {
      setOverwatch(null)
      return
    }
    let cancelled = false
    getOverwatch(game.id)
      .then((o) => !cancelled && setOverwatch(o.seat === null ? null : o))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
  }, [game, endOfMovement, shots])
  // Picking a unit to fire and its target, as when shooting.
  const overwatching = overwatch !== null

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
  const shootingUnit = (overwatching ? overwatch : shooting)?.units.find(
    (u) => u.unit_id === shootingFocus.unitId
  )
  const bubbleUnitId =
    (shootingPhase || overwatching) && shootingUnit?.can_shoot ? shootingUnit.unit_id : null
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

  // Where the drafted unit's models can reach, going round walls (for the
  // movement bubble): asked for whenever their starts or distances change.
  const [reach, setReach] = useState(null)
  const draftRings = moveRings(deployment, movement, draft)
  const currentReachKey = draftRings.length > 0 ? reachKey(draft.unitId, draftRings) : null
  useEffect(() => {
    if (currentReachKey === null || !game) return
    let cancelled = false
    getReach(game.id, {
      unit_id: draft.unitId,
      models: draftRings.map((r) => ({ unit_model_id: r.id, x: r.x, y: r.y, distance: r.r })),
    })
      .then((r) => !cancelled && setReach({ key: currentReachKey, models: r.models }))
      .catch((err) => setError(err.message))
    return () => {
      cancelled = true
    }
    // Only when what it's for changes (the key says).
  }, [currentReachKey])

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
  // counts). A move that's fine is saved straight away if `save`.
  const runCheck = async (unitId, positions, kind = null, targetId = null, save = false) => {
    if (kind === 'charge' && targetId === null) return
    const seq = ++checkSeq.current
    setChecking(true)
    try {
      let check
      if (kind === 'reinforce') {
        check = await checkArrival(game.id, asPayload(unitId, positions))
      } else if (kind === 'disembark') {
        check = await checkDisembark(game.id, asPayload(unitId, positions))
      } else if (kind === 'reanimate') {
        check = await checkReanimation(game.id, asPayload(unitId, positions))
      } else if (kind === 'consolidate') {
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
      if (seq !== checkSeq.current) return
      setDraft((d) => (d.unitId === unitId ? { ...d, check } : d))
      if (save && check.valid && MOVE_KINDS.includes(kind)) {
        await saveMove(unitId, positions, kind)
      }
    } catch (err) {
      if (seq === checkSeq.current) setError(err.message)
    } finally {
      if (seq === checkSeq.current) setChecking(false)
    }
  }

  const setDown = async (x, y) => {
    const { unitId, kind } = draftRef.current
    setError(null)
    try {
      // Deploying, a unit arriving from Reserves (kind 'reinforce') or one
      // disembarking (kind 'disembark').
      const getFormation =
        kind === 'reinforce'
          ? getReservesFormation
          : kind === 'disembark'
            ? getDisembarkFormation
            : getDeploymentFormation
      const formation = await getFormation(game.id, { unit_id: unitId, x, y })
      const positions = Object.fromEntries(
        formation.map((p) => [p.unit_model_id, { x: p.x, y: p.y, rotation: p.rotation }])
      )
      setDraft({ unitId, positions, check: null, kind: kind ?? null })
      runCheck(unitId, positions, kind ?? null)
    } catch (err) {
      setError(err.message)
    }
  }

  // A dragged model follows the pointer - while moving, only as far as its
  // ring (the backend still checks the distance).
  // A dragged model follows the pointer - only as far as its ring while
  // moving, and never onto another base: it's pushed out to just touching
  // the base under the pointer, or if there's no room there, it slides
  // towards the pointer until it touches one. The backend still checks it all.
  const movePiece = (id, x, y) => {
    const current = draftRef.current
    const ring = moveRings(deployment, movement, current).find((r) => r.id === id)
    const limit = (px, py) => {
      const to = ring ? tethered(ring, px, py) : { x: px, y: py }
      return [to.x, to.y]
    }
    const pieces = boardPieces(game, deployment, current).filter((p) => !p.ghost)
    const base = pieces.find((p) => p.id === id)
    if (!base) return
    const others = pieces.filter((p) => p.id !== id)
    const [nx, ny] =
      freeSpot(base, x, y, others, limit) ?? slide(base, base.x, base.y, x, y, others, limit)
    setDraft((d) => ({
      ...d,
      positions: { ...d.positions, [id]: { ...d.positions[id], x: nx, y: ny } },
    }))
  }

  // Turning a dragged oval base by a corner handle - unless that would put
  // it over another base. (The backend still checks it all.)
  const rotatePiece = (id, rotation) => {
    const pieces = boardPieces(game, deployment, draftRef.current).filter((p) => !p.ghost)
    const base = pieces.find((p) => p.id === id)
    if (!base) return
    const turned = { ...base, rotation }
    if (pieces.some((p) => p.id !== id && basesOverlap(turned, p))) return
    setDraft((d) => ({
      ...d,
      positions: { ...d.positions, [id]: { ...d.positions[id], rotation } },
    }))
  }

  // Clicking a model picks its unit in the phase's panel, as its radio would:
  // one of the acting player's units to act with - or, with one picked, an
  // enemy unit to shoot or fight (the panel ignores one that isn't a valid
  // target). Clicking the unit already picked does nothing (a drag ends in a
  // click).
  const pickUnit = (unitId) => {
    if (overwatching) {
      pickFocus(overwatch.units.some((u) => u.unit_id === unitId), unitId)
    } else if (moving && movement) {
      const unit = movement.units.find((u) => u.unit_id === unitId)
      if (unit && unit.unit_id !== draftRef.current.unitId) selectMoveUnit(unit)
    } else if (chargePhase && charge) {
      const unit = charge.units.find((u) => u.unit_id === unitId)
      if (unit && unit.unit_id !== draftRef.current.unitId) startCharge(unit)
    } else if (fightPhase && fightState?.step === 'pile_in' && pileIn) {
      const unit = pileIn.units.find((u) => u.unit_id === unitId)
      if (unit?.can_pile_in && unit.unit_id !== draftRef.current.unitId) startPileIn(unit)
    } else if (shootingPhase && shooting) {
      pickFocus(shooting.units.some((u) => u.unit_id === unitId), unitId)
    } else if (fighting && fightState) {
      const unit = fightState.units.find((u) => u.unit_id === unitId)
      if (!unit) return
      // The picking player's unit: only one that can fight now.
      if (unit.seat === fightState.seat && !unit.can_fight) return
      pickFocus(unit.seat === fightState.seat, unitId)
    }
  }

  // Shooting and fighting: a unit of the acting player's to act with, or -
  // once one's picked - an enemy target.
  const pickFocus = (ownUnit, unitId) => {
    if (ownUnit) {
      if (unitId !== shootingFocus.unitId) setShootingFocus({ unitId, targetId: null })
    } else if (shootingFocus.unitId !== null) {
      setShootingFocus({ ...shootingFocus, targetId: unitId })
    }
  }

  runCheckRef.current = runCheck

  const dropPiece = () => {
    const { unitId, positions, kind, targetId } = draftRef.current
    // In the movement phase, a valid move is saved as soon as it's made.
    if (positions) runCheck(unitId, positions, kind, targetId ?? null, moving)
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

  // Where a unit's models were at the start of the movement phase.
  const phaseStarts = (unit) =>
    Object.fromEntries(
      unit.models.filter((m) => m.start).map((m) => [m.unit_model_id, m.start])
    )

  // Any unit can be picked - and moved again until the phase ends.
  const selectMoveUnit = (unit) => {
    checkSeq.current++
    // As it moved; or within Engagement Range it Falls Back; otherwise it
    // moves normally, or Advances if it's rolled to.
    let kind = unit.advance_roll ? 'advance' : 'normal'
    if (unit.allowed_kinds.includes('fall_back')) kind = 'fall_back'
    if (unit.moved) kind = unit.kind
    const positions = startPositions(unit.unit_id)
    setDraft({ unitId: unit.unit_id, positions, check: null, kind, starts: phaseStarts(unit) })
    runCheck(unit.unit_id, positions, kind)
  }

  // Saves a valid move (when a model's dropped, or a moved unit's move
  // changes kind): no Move button - it's locked when the phase ends.
  const saveMove = async (unitId, positions, kind) => {
    try {
      await moveUnit(game.id, { ...asPayload(unitId, positions), kind })
      setGame(await getGame(game.id))
    } catch (err) {
      setError(err.message)
    }
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
    // A unit that's already moved keeps its move, now of this kind.
    const moved = movement?.units.find((u) => u.unit_id === current.unitId)?.moved
    runCheck(current.unitId, positions, kind, null, Boolean(moved))
  }

  // Ticking Advance rolls the unit's D6 (the backend keeps it for the
  // phase), and from then on it Advances: it can't be unticked.
  const toggleAdvance = async (unit, on) => {
    if (!on) {
      if (!unit.advance_roll) chooseKind('normal')
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

  const resetMove = async () => {
    const { unitId, kind, starts } = draftRef.current
    checkSeq.current++
    const moved = movement?.units.find((u) => u.unit_id === unitId)?.moved
    if (moved && !(await act(() => resetMoveApi(game.id, { unit_id: unitId })))) return
    const positions = Object.fromEntries(
      Object.entries(starts ?? startPositions(unitId)).map(([id, p]) => [
        id,
        { x: p.x, y: p.y, rotation: p.rotation },
      ])
    )
    setDraft((d) => ({ ...d, positions, check: null }))
    runCheck(unitId, positions, kind)
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
  // Before a battle round's first turn, if any rules happen at its start.
  const roundStart = game.phase === 'start_of_round'
  let advanceLabel = 'Next phase'
  if (roundStart) advanceLabel = 'Begin the first turn'
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
      {game.status === 'deployment' && game.deployment_step === 'formations' && (
        <FormationsPanel
          game={game}
          onDeclared={(seat) => act(() => declareFormations(game.id, { seat }))}
          onError={setError}
        />
      )}
      {game.status === 'deployment' && game.deployment_step !== 'formations' && (
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
            {roundStart && <li className="current">Start of round</li>}
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
        <ReservesPanel
          game={game}
          reserves={reserves}
          draft={draft}
          checking={checking}
          onSelectUnit={(unitId) => {
            checkSeq.current++
            setDraft({ ...NO_DRAFT, unitId, kind: 'reinforce' })
          }}
          onPickUp={() => {
            checkSeq.current++
            setDraft((d) => ({ ...NO_DRAFT, unitId: d.unitId, kind: 'reinforce' }))
          }}
          onBringIn={async () => {
            const { unitId, positions } = draftRef.current
            if (await act(() => bringIn(game.id, asPayload(unitId, positions)))) {
              setDraft(NO_DRAFT)
            }
          }}
        />
      )}
      {moving && !endOfMovement && (
        <EmbarkedPanel
          game={game}
          embarked={embarked}
          draft={draft}
          checking={checking}
          onSelectUnit={(unitId) => {
            checkSeq.current++
            setDraft({ ...NO_DRAFT, unitId, kind: 'disembark' })
          }}
          onPickUp={() => {
            checkSeq.current++
            setDraft((d) => ({ ...NO_DRAFT, unitId: d.unitId, kind: 'disembark' }))
          }}
          onDisembark={async () => {
            const { unitId, positions } = draftRef.current
            if (await act(() => disembark(game.id, asPayload(unitId, positions)))) {
              setDraft(NO_DRAFT)
            }
          }}
        />
      )}
      <MissionPanel
        game={game}
        mission={mission}
        onAnswered={(m) => {
          setMission(m)
          getGame(game.id)
            .then(setGame)
            .catch((err) => setError(err.message))
        }}
        onError={setError}
      />
      <ScoringPanel game={game} onAction={act} onError={setError} />
      {battleShock &&
        (battleShock.pending.length > 0 ||
          battleShock.taken.length > 0 ||
          battleShock.battle_shocked.length > 0 ||
          commandPhase) && (
          <BattleShockPanel
            game={game}
            battleShock={battleShock}
            deployment={deployment}
            onChange={(b) => {
              setBattleShock(b)
              // The game again: CP spent, OC changed.
              getGame(game.id)
                .then(setGame)
                .catch((err) => setError(err.message))
            }}
            onError={setError}
          />
        )}
      {commandPhase && !reanimation?.placing && <CommandPanel game={game} onError={setError} />}
      {commandPhase && (
        <ReanimationPanel
          game={game}
          reanimation={reanimation}
          draft={draft}
          checking={checking}
          onSelectUnit={(unit) => {
            checkSeq.current++
            // Its returned models start where the backend suggests.
            const positions = Object.fromEntries(
              unit.to_place.map((p) => [p.unit_model_id, { x: p.x, y: p.y, rotation: p.rotation }])
            )
            setDraft({ ...NO_DRAFT, unitId: unit.unit_id, positions, kind: 'reanimate' })
            runCheck(unit.unit_id, positions, 'reanimate')
          }}
          onPlace={async () => {
            const { unitId, positions } = draftRef.current
            if (await act(() => placeReanimated(game.id, asPayload(unitId, positions)))) {
              setDraft(NO_DRAFT)
            }
          }}
        />
      )}
      {overwatching && (
        <ShootingPanel
          game={game}
          player={game.players.find((p) => p.seat === overwatch.seat)}
          shooting={overwatch}
          overwatch={overwatch}
          focus={shootingFocus}
          onFocus={setShootingFocus}
          onShot={() => {
            // The game again: CP spent, destroyed models off the battlefield.
            setShots((n) => n + 1)
            getGame(game.id)
              .then(setGame)
              .catch((err) => setError(err.message))
          }}
          onError={setError}
        />
      )}
      {moving && !endOfMovement && (
        <MovementPanel
          player={turnPlayer}
          movement={movement}
          draft={draft}
          checking={checking}
          onSelectUnit={selectMoveUnit}
          onToggleAdvance={toggleAdvance}
          onReset={resetMove}
        />
      )}
      {roundStart && <RoundStartPanel game={game} onError={setError} />}
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
          shootingPhase || fighting || overwatching
            ? shootingFocus
            : chargePhase
              ? { targetId: draft.targetId }
              : {}
        )}
        rings={moveRings(deployment, movement, draft)}
        auras={auraCircles(deployment, draft)}
        objectiveControl={objectiveControl(game, deployment)}
        territoryLine={deployment?.territory?.line ?? null}
        markers={(mission?.markers ?? []).map((m) => ({
          id: m.id,
          x: m.x,
          y: m.y,
          side: m.seat === game.attacker_seat ? 'attacker' : 'defender',
          title: `${game.players.find((p) => p.seat === m.seat)?.user_name}'s operation marker (${m.source}) - ${m.label}`,
        }))}
        areaLabels={Object.fromEntries(
          (mission?.prompts ?? [])
            .filter((p) => p.kind === 'place_markers')
            .flatMap((p) => p.options.map((o) => [o.id, o.label.split(' ')[0]]))
        )}
        bubbles={[
          (moving || chargePhase || fightPhase) &&
            moveBubble(deployment, movement, draft, reach),
          sightBubble && { kind: 'shoot', regions: sightBubble.regions },
        ].filter(Boolean)}
        onBoardClick={
          (game.status === 'deployment' ||
            draft.kind === 'reinforce' ||
            draft.kind === 'disembark') &&
          draft.unitId !== null &&
          draft.positions === null
            ? setDown
            : null
        }
        onPieceMove={movePiece}
        onPieceRotate={rotatePiece}
        onPieceClick={moving || chargePhase || fightPhase || shootingPhase ? pickUnit : null}
        onPieceDrop={dropPiece}
      />
      {layoutId === null && (
        <p className="hint">
          No terrain layout for {attacker?.disposition_name ?? '—'} (attacker) vs{' '}
          {defender?.disposition_name ?? '—'} (defender) yet.
        </p>
      )}

      {game.status === 'in_progress' && (
        <TurnRecord game={game} deployment={deployment} onError={setError} />
      )}
      {(game.status === 'in_progress' || game.status === 'finished') && (
        <ScoreHistory game={game} />
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
