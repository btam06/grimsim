import { faChessRook, faFlag, faSkull } from '@fortawesome/free-solid-svg-icons'
import { useRef } from 'react'

// The battlefield, drawn at a fixed scale: every inch on the table is
// PX_PER_INCH pixels on screen, so the board keeps the table's proportions
// (and anything placed on it later can use table inches directly - the SVG's
// own coordinates are inches).
export const BOARD_WIDTH_INCHES = 60
export const BOARD_HEIGHT_INCHES = 44
export const PX_PER_INCH = 20

// Faint lines every GRID_INCHES (1" squares), to help judge distances by eye.
const GRID_INCHES = 1

// A layout's terrain (see GET /terrain-layouts/{id}): its terrain areas
// (baseplates: rectangles positioned by their centre, or polygons whose points
// are relative to their position) and terrain features (ruin walls
// and obstacles, each made of rectangles placed relative to its position),
// turned clockwise by their rotation - all in inches, like the board.
function Terrain({ layout }) {
  // Objectives are terrain areas: those are outlined more heavily.
  const objectiveAreas = new Set((layout.objectives ?? []).flatMap((o) => o.area_ids))
  const areaClass = (a) =>
    `terrain-area${objectiveAreas.has(a.id) ? ' terrain-area--objective' : ''}`
  return (
    <g className="terrain">
      {layout.areas.map((a) =>
        a.points.length > 0 ? (
          // A polygon: its points are relative to its position.
          <polygon
            key={`area-${a.id}`}
            className={areaClass(a)}
            points={a.points.map((p) => `${p.x},${p.y}`).join(' ')}
            transform={`translate(${a.x} ${a.y}) rotate(${a.rotation})`}
          />
        ) : (
          <rect
            key={`area-${a.id}`}
            className={areaClass(a)}
            x={a.x - a.width / 2}
            y={a.y - a.height / 2}
            width={a.width}
            height={a.height}
            transform={`rotate(${a.rotation} ${a.x} ${a.y})`}
          />
        )
      )}
      {layout.features.map((f) => (
        <g
          key={`feature-${f.id}`}
          className={`terrain-feature terrain-feature--${f.kind}`}
          transform={`translate(${f.x} ${f.y}) rotate(${f.rotation})`}
        >
          {f.parts.map((p, i) => (
            <rect key={i} x={p.x} y={p.y} width={p.width} height={p.height} />
          ))}
        </g>
      ))}
    </g>
  )
}

// A layout's deployment zones (see GET /terrain-layouts/{id}): the attacker's
// and the defender's, each a polygon in board inches.
const DEPLOYMENT_SIDES = ['attacker', 'defender']

function Deployment({ deployment }) {
  return (
    <g className="deployment">
      {DEPLOYMENT_SIDES.map((side) => (
        <polygon
          key={side}
          className={`deployment-zone deployment-zone--${side}`}
          points={deployment[`${side}_zone`].map((p) => `${p.x},${p.y}`).join(' ')}
        />
      ))}
    </g>
  )
}

// The objectives' markers, as on the layout cards: a home (each side's
// colour), an expansion or the centre.
const OBJECTIVE_ICONS = {
  attacker_home: faChessRook,
  defender_home: faChessRook,
  expansion: faFlag,
  centre: faSkull,
}
const OBJECTIVE_NAMES = {
  attacker_home: "Attacker's home objective",
  defender_home: "Defender's home objective",
  expansion: 'Expansion objective',
  centre: 'Centre objective',
}
const MARKER_RADIUS = 1.4

function ObjectiveMarkers({ objectives }) {
  return (
    <g className="objectives">
      {objectives.map((o) => {
        const [width, height, , , path] = OBJECTIVE_ICONS[o.kind].icon
        const scale = (MARKER_RADIUS * 1.1) / Math.max(width, height)
        const left = o.x - (width * scale) / 2
        const top = o.y - (height * scale) / 2
        return (
          <g key={o.id} className={`objective objective--${o.kind}`}>
            <title>{OBJECTIVE_NAMES[o.kind]}</title>
            <circle cx={o.x} cy={o.y} r={MARKER_RADIUS} />
            <path
              d={Array.isArray(path) ? path.join(' ') : path}
              transform={`translate(${left} ${top}) scale(${scale})`}
            />
          </g>
        )
      })}
    </g>
  )
}

// Models on the board: each a base (an ellipse, rx/ry its half width and
// height in inches) centred on (x, y), turned `rotation` degrees clockwise,
// coloured by side. Draft pieces (a unit being placed) can be dragged; invalid
// ones are marked; ghosts show where a moving unit's models started.
function Pieces({ pieces, onPointerDown }) {
  return (
    <g className="pieces">
      {pieces.map((p) => (
        <ellipse
          key={p.id}
          className={[
            'piece',
            `piece--${p.side}`,
            p.draft && 'piece--draft',
            p.invalid && 'piece--invalid',
            p.ghost && 'piece--ghost',
            p.shooter && 'piece--shooter',
            p.target && 'piece--target',
          ]
            .filter(Boolean)
            .join(' ')}
          cx={p.x}
          cy={p.y}
          rx={p.rx}
          ry={p.ry}
          transform={p.rotation ? `rotate(${p.rotation} ${p.x} ${p.y})` : undefined}
          onPointerDown={p.draft ? (e) => onPointerDown(e, p) : undefined}
          onClick={(e) => e.stopPropagation()}
        >
          <title>{p.title}</title>
        </ellipse>
      ))}
    </g>
  )
}

// `attacker` and `defender` name whose zone is whose in the legend.
// `bubbles` shade where a unit can reach - {kind: 'move', circles: [{id, x,
// y, r}]} or {kind: 'shoot', regions: [[{x, y}]]} - each drawn as one shape.
// `rings` ({id, x, y, r} in inches) mark how far each moving model can go
// from where it started, with a tether to where it is now (`to`, if moved).
// `onBoardClick(x, y)`, if given, is called with the inches clicked;
// `onPieceMove(id, x, y)` while a draft piece is dragged, and
// `onPieceDrop(id)` when it's let go.
function Gameboard({
  layout = null,
  attacker = null,
  defender = null,
  pieces = [],
  rings = [],
  bubbles = [],
  onBoardClick = null,
  onPieceMove = null,
  onPieceDrop = null,
}) {
  const deployment = layout?.deployment ?? null
  const svgRef = useRef(null)
  // The piece being dragged, and where on it it was picked up.
  const dragging = useRef(null)

  // A pointer event's position in board inches.
  const toInches = (e) => {
    const svg = svgRef.current
    const point = svg.createSVGPoint()
    point.x = e.clientX
    point.y = e.clientY
    const { x, y } = point.matrixTransform(svg.getScreenCTM().inverse())
    return { x, y }
  }

  const startDrag = (e, piece) => {
    e.stopPropagation()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const { x, y } = toInches(e)
    dragging.current = { id: piece.id, dx: x - piece.x, dy: y - piece.y }
  }

  const moveDrag = (e) => {
    const drag = dragging.current
    if (!drag) return
    const { x, y } = toInches(e)
    const clamp = (value, max) => Math.min(Math.max(value, 0), max)
    onPieceMove?.(
      drag.id,
      clamp(x - drag.dx, BOARD_WIDTH_INCHES),
      clamp(y - drag.dy, BOARD_HEIGHT_INCHES)
    )
  }

  const endDrag = () => {
    const drag = dragging.current
    if (!drag) return
    dragging.current = null
    onPieceDrop?.(drag.id)
  }
  const verticals = []
  for (let x = GRID_INCHES; x < BOARD_WIDTH_INCHES; x += GRID_INCHES) verticals.push(x)
  const horizontals = []
  for (let y = GRID_INCHES; y < BOARD_HEIGHT_INCHES; y += GRID_INCHES) horizontals.push(y)

  // Wider than the page's column: the board breaks out of it, centred, up to
  // the window's width (see .gameboard).
  const widthPx = BOARD_WIDTH_INCHES * PX_PER_INCH
  return (
    <div className="gameboard" style={{ '--board-width': `${widthPx}px` }}>
      <svg
        ref={svgRef}
        className={`gameboard-svg${onBoardClick ? ' gameboard-svg--placing' : ''}`}
        onClick={
          onBoardClick
            ? (e) => {
                const { x, y } = toInches(e)
                onBoardClick(x, y)
              }
            : undefined
        }
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        width={widthPx}
        height={BOARD_HEIGHT_INCHES * PX_PER_INCH}
        viewBox={`0 0 ${BOARD_WIDTH_INCHES} ${BOARD_HEIGHT_INCHES}`}
        role="img"
        aria-label={`Battlefield, ${BOARD_WIDTH_INCHES}" by ${BOARD_HEIGHT_INCHES}"`}
      >
        <rect
          className="gameboard-surface"
          x={0}
          y={0}
          width={BOARD_WIDTH_INCHES}
          height={BOARD_HEIGHT_INCHES}
        />
        {deployment && <Deployment deployment={deployment} />}
        {verticals.map((x) => (
          <line key={`v${x}`} className="gameboard-grid" x1={x} y1={0} x2={x} y2={BOARD_HEIGHT_INCHES} />
        ))}
        {horizontals.map((y) => (
          <line key={`h${y}`} className="gameboard-grid" x1={0} y1={y} x2={BOARD_WIDTH_INCHES} y2={y} />
        ))}
        {layout && (
          <defs>
            <pattern
              id="terrain-hatch"
              patternUnits="userSpaceOnUse"
              width="1"
              height="1"
              patternTransform="rotate(45)"
            >
              <line className="terrain-hatch-line" x1="0" y1="0" x2="0" y2="1" />
            </pattern>
          </defs>
        )}
        {/* The centre lines. */}
        <line
          className="gameboard-centre"
          x1={BOARD_WIDTH_INCHES / 2}
          y1={0}
          x2={BOARD_WIDTH_INCHES / 2}
          y2={BOARD_HEIGHT_INCHES}
        />
        <line
          className="gameboard-centre"
          x1={0}
          y1={BOARD_HEIGHT_INCHES / 2}
          x2={BOARD_WIDTH_INCHES}
          y2={BOARD_HEIGHT_INCHES / 2}
        />
        {layout && <Terrain layout={layout} />}
        {layout && <ObjectiveMarkers objectives={layout.objectives ?? []} />}
        {bubbles.map((b) => (
          // Faded as a group, so where its shapes overlap isn't darker.
          <g key={b.kind} className={`bubble bubble--${b.kind}`}>
            {(b.circles ?? []).map((c) => (
              <circle key={c.id} cx={c.x} cy={c.y} r={c.r} />
            ))}
            {(b.regions ?? []).map((region, i) => (
              <polygon key={i} points={region.map((p) => `${p.x},${p.y}`).join(' ')} />
            ))}
          </g>
        ))}
        {rings.map((r) => (
          <g key={`ring-${r.id}`}>
            <circle className="move-range" cx={r.x} cy={r.y} r={r.r} />
            {r.to && (r.to.x !== r.x || r.to.y !== r.y) && (
              <line className="move-tether" x1={r.x} y1={r.y} x2={r.to.x} y2={r.to.y} />
            )}
          </g>
        ))}
        <Pieces pieces={pieces} onPointerDown={startDrag} />
      </svg>
      {deployment && (
        <p className="deployment-legend">
          {deployment.name}:{' '}
          {DEPLOYMENT_SIDES.map((side) => (
            <span key={side} className="deployment-legend-item">
              <span className={`deployment-swatch deployment-zone--${side}`} aria-hidden="true" />
              {side === 'attacker' ? 'Attacker' : 'Defender'}
              {(side === 'attacker' ? attacker : defender) &&
                ` (${side === 'attacker' ? attacker : defender})`}
            </span>
          ))}
        </p>
      )}
      <p className="hint">
        {layout ? `${layout.name} · ` : ''}
        {BOARD_WIDTH_INCHES}" × {BOARD_HEIGHT_INCHES}" · 1" = {PX_PER_INCH}px · grid every{' '}
        {GRID_INCHES}"
      </p>
    </div>
  )
}

export default Gameboard
