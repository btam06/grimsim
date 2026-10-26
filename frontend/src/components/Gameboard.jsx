import { faChessRook, faFlag, faRotate, faSkull } from '@fortawesome/free-solid-svg-icons'
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
//
// `control` ({area id: {side, title}}) marks objectives a player controls:
// their areas are lightly shaded in that player's colour.
function areaShape(a, key, className, title = null) {
  return a.points.length > 0 ? (
    // A polygon: its points are relative to its position.
    <polygon
      key={key}
      className={className}
      points={a.points.map((p) => `${p.x},${p.y}`).join(' ')}
      transform={`translate(${a.x} ${a.y}) rotate(${a.rotation})`}
    >
      {title && <title>{title}</title>}
    </polygon>
  ) : (
    <rect
      key={key}
      className={className}
      x={a.x - a.width / 2}
      y={a.y - a.height / 2}
      width={a.width}
      height={a.height}
      transform={`rotate(${a.rotation} ${a.x} ${a.y})`}
    >
      {title && <title>{title}</title>}
    </rect>
  )
}

function Terrain({ layout, control = {} }) {
  // Objectives are terrain areas: those are outlined more heavily.
  const objectiveAreas = new Set((layout.objectives ?? []).flatMap((o) => o.area_ids))
  const areaClass = (a) =>
    `terrain-area${objectiveAreas.has(a.id) ? ' terrain-area--objective' : ''}`
  return (
    <g className="terrain">
      {/* Controlled objectives' shading, under the areas' hatching. */}
      {layout.areas.map(
        (a) =>
          control[a.id]?.side &&
          areaShape(a, `held-${a.id}`, `objective-held objective-held--${control[a.id].side}`)
      )}
      {layout.areas.map((a) =>
        areaShape(a, `area-${a.id}`, areaClass(a), control[a.id]?.title ?? null)
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

// The cursor over a base's rotation handles: Font Awesome's rotate icon, dark
// with a light outline so it shows on any background.
const ROTATE_CURSOR = (() => {
  const [width, height, , , path] = faRotate.icon
  const d = Array.isArray(path) ? path.join(' ') : path
  const pad = 40
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" ` +
    `viewBox="${-pad} ${-pad} ${width + 2 * pad} ${height + 2 * pad}">` +
    `<path d="${d}" fill="#111" stroke="#fff" stroke-width="40" paint-order="stroke"/></svg>`
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 11 11, crosshair`
})()
// How big a rotation handle is (inches).
const HANDLE_RADIUS = 0.3

// A draggable oval base's rotation handles: one at each corner of its box
// (top left, top right, bottom left, bottom right), turning with it. Round
// bases don't get them - turning one changes nothing.
function RotateHandles({ pieces, onPointerDown }) {
  return (
    <g className="rotate-handles">
      {pieces
        .filter((p) => p.draft && p.rx !== p.ry)
        .flatMap((p) => {
          const angle = ((p.rotation ?? 0) * Math.PI) / 180
          return [
            [-1, -1],
            [1, -1],
            [-1, 1],
            [1, 1],
          ].map(([sx, sy]) => {
            const u = sx * p.rx
            const v = sy * p.ry
            return (
              <circle
                key={`${p.id}-${sx}-${sy}`}
                className="rotate-handle"
                data-piece={p.id}
                cx={p.x + u * Math.cos(angle) - v * Math.sin(angle)}
                cy={p.y + u * Math.sin(angle) + v * Math.cos(angle)}
                r={HANDLE_RADIUS}
                style={{ cursor: ROTATE_CURSOR }}
                onPointerDown={(e) => onPointerDown(e, p)}
                onClick={(e) => e.stopPropagation()}
              >
                <title>Drag to turn the base</title>
              </circle>
            )
          })
        })}
    </g>
  )
}

// A model's base: an ellipse (rx/ry its half width and height in inches) - or
// a rectangle, for a hull measured as a box (`box`) - centred on (x, y),
// turned `rotation` degrees clockwise.
function Base({ piece: p, className, onPointerDown, onClick }) {
  const transform = p.rotation ? `rotate(${p.rotation} ${p.x} ${p.y})` : undefined
  const shape = { className, transform, onPointerDown, onClick }
  if (p.box) {
    return (
      <rect
        {...shape}
        x={p.x - p.rx}
        y={p.y - p.ry}
        width={p.rx * 2}
        height={p.ry * 2}
      >
        <title>{p.title}</title>
      </rect>
    )
  }
  return (
    <ellipse {...shape} cx={p.x} cy={p.y} rx={p.rx} ry={p.ry}>
      <title>{p.title}</title>
    </ellipse>
  )
}

// Models on the board: each a base (see Base) centred on (x, y), turned
// `rotation` degrees clockwise,
// coloured by side. Draft pieces (a unit being placed) can be dragged; invalid
// ones are marked; ghosts show where a moving unit's models started.
function Pieces({ pieces, onPointerDown, onClick }) {
  return (
    <g className="pieces">
      {pieces.map((p) => (
        <Base
          key={p.id}
          piece={p}
          className={[
            'piece',
            `piece--${p.side}`,
            p.draft && 'piece--draft',
            p.invalid && 'piece--invalid',
            p.ghost && 'piece--ghost',
            p.shooter && 'piece--shooter',
            p.target && 'piece--target',
            p.shocked && 'piece--shocked',
            onClick && !p.ghost && !p.draft && 'piece--clickable',
          ]
            .filter(Boolean)
            .join(' ')}
          onPointerDown={p.draft ? (e) => onPointerDown(e, p) : undefined}
          onClick={(e) => {
            e.stopPropagation()
            if (onClick && !p.ghost && p.unitId !== undefined) onClick(p.unitId)
          }}
        />
      ))}
    </g>
  )
}

// Where an aura's label goes across: over its model, but kept on the board
// (about 0.38" a character at its size).
function auraLabelX(aura) {
  const half = ((aura.name.length + 4) * 0.38) / 2
  return Math.min(Math.max(aura.x, half), BOARD_WIDTH_INCHES - half)
}

// `attacker` and `defender` name whose zone is whose in the legend.
// `bubbles` shade where a unit can reach - {kind: 'move', circles: [{id, x,
// y, r}]} or {kind: 'shoot', regions: [[{x, y}]]} - each drawn as one shape.
// `rings` ({id, x, y, r} in inches) mark how far each moving model can go
// from where it started, with a tether to where it is now (`to`, if moved) -
// along `path` (points) where it goes round walls.
// `objectiveControl` ({area id: {side, title}}) shades each controlled
// objective's areas in its controller's colour (see Terrain).
// `markers` ({id, x, y, side, title}) are operation markers, drawn as small
// diamonds in their player's colour; `areaLabels` ({area id: text}) label
// terrain areas at their middle (e.g. while picking some).
// `territoryLine` ([{x, y}, {x, y}]) is the line between the players'
// territories, drawn over the centre lines.
// `auras` ({id, x, y, rx, ry, rotation, range, name, colour} in inches) draw
// how far an aura reaches from a model's base: its base grown by `range` all
// round, labelled.
// `onBoardClick(x, y)`, if given, is called with the inches clicked;
// `onPieceMove(id, x, y)` while a draft piece is dragged, `onPieceRotate(id,
// rotation)` while it's turned by a corner handle (degrees clockwise), and
// `onPieceDrop(id)` when it's let go. `onPieceClick(unitId)` when a model is
// clicked (to pick its unit).
function Gameboard({
  layout = null,
  attacker = null,
  defender = null,
  pieces = [],
  rings = [],
  bubbles = [],
  auras = [],
  objectiveControl = {},
  territoryLine = null,
  markers = [],
  areaLabels = {},
  onBoardClick = null,
  onPieceMove = null,
  onPieceRotate = null,
  onPieceDrop = null,
  onPieceClick = null,
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

  // Turning a base by a corner handle: it follows the pointer round its
  // centre, from the angle it was picked up at.
  const pointerAngle = (piece, x, y) => (Math.atan2(y - piece.y, x - piece.x) * 180) / Math.PI
  const startRotate = (e, piece) => {
    e.stopPropagation()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const { x, y } = toInches(e)
    dragging.current = {
      id: piece.id,
      rotating: true,
      x: piece.x,
      y: piece.y,
      offset: pointerAngle(piece, x, y) - (piece.rotation ?? 0),
    }
  }

  const moveDrag = (e) => {
    const drag = dragging.current
    if (!drag) return
    const { x, y } = toInches(e)
    if (drag.rotating) {
      const turned = pointerAngle(drag, x, y) - drag.offset
      // Kept within (-180, 180], to the degree.
      onPieceRotate?.(drag.id, Math.round(((((turned + 180) % 360) + 360) % 360) - 180))
      return
    }
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
        {/* The line between the players' territories (a diagonal for
            Search and Destroy). */}
        {territoryLine && (
          <line
            className="gameboard-territory"
            x1={territoryLine[0].x}
            y1={territoryLine[0].y}
            x2={territoryLine[1].x}
            y2={territoryLine[1].y}
          >
            <title>Territory line</title>
          </line>
        )}
        {layout && <Terrain layout={layout} control={objectiveControl} />}
        {layout && <ObjectiveMarkers objectives={layout.objectives ?? []} />}
        {bubbles.map((b) => (
          // Faded as a group, so where its shapes overlap isn't darker.
          <g key={b.kind} className={`bubble bubble--${b.kind}`}>
            {(b.circles ?? []).map((c) => (
              <circle key={c.id} cx={c.x} cy={c.y} r={c.r} />
            ))}
            {(b.regions ?? []).map((region, i) => {
              // A region is its points - or {points, inflate}: widened by
              // `inflate` inches all round (a base's reach past its centre).
              const points = Array.isArray(region) ? region : region.points
              const inflate = Array.isArray(region) ? 0 : region.inflate
              return (
                <polygon
                  key={i}
                  points={points.map((p) => `${p.x},${p.y}`).join(' ')}
                  strokeWidth={inflate ? 2 * inflate : undefined}
                  className={inflate ? 'bubble-inflated' : undefined}
                />
              )
            })}
          </g>
        ))}
        {layout &&
          layout.areas
            .filter((a) => areaLabels[a.id])
            .map((a) => (
              <text key={`area-label-${a.id}`} className="area-label" x={a.x} y={a.y}>
                {areaLabels[a.id]}
              </text>
            ))}
        {markers.map((m) => (
          <g key={`marker-${m.id}`} className={`operation-marker operation-marker--${m.side}`}>
            <polygon
              points={`${m.x},${m.y - 0.6} ${m.x + 0.6},${m.y} ${m.x},${m.y + 0.6} ${m.x - 0.6},${m.y}`}
            >
              <title>{m.title}</title>
            </polygon>
          </g>
        ))}
        {auras.map((a) => (
          <g key={`aura-${a.id}`} className={`aura aura--${a.colour}`}>
            <ellipse
              cx={a.x}
              cy={a.y}
              rx={a.rx + a.range}
              ry={a.ry + a.range}
              transform={`rotate(${a.rotation ?? 0} ${a.x} ${a.y})`}
            >
              <title>{`${a.name}: ${a.range}"`}</title>
            </ellipse>
            <text
              x={auraLabelX(a)}
              y={Math.max(0.8, a.y - Math.max(a.rx, a.ry) - a.range - 0.3)}
              textAnchor="middle"
            >
              {`${a.name} ${a.range}"`}
            </text>
          </g>
        ))}
        {rings.map((r) => (
          <g key={`ring-${r.id}`}>
            <circle className="move-range" cx={r.x} cy={r.y} r={r.r} />
            {/* The way it went: round walls if the backend found it does, or
                straight. */}
            {r.path ? (
              <polyline
                className="move-tether"
                points={r.path.map((p) => `${p.x},${p.y}`).join(' ')}
              />
            ) : (
              r.to &&
              (r.to.x !== r.x || r.to.y !== r.y) && (
                <line className="move-tether" x1={r.x} y1={r.y} x2={r.to.x} y2={r.to.y} />
              )
            )}
          </g>
        ))}
        <Pieces pieces={pieces} onPointerDown={startDrag} onClick={onPieceClick} />
        <RotateHandles pieces={pieces} onPointerDown={startRotate} />
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
