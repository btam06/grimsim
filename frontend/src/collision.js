// Keeping a dragged base off the others: bases are ellipses (round ones
// just have rx === ry) - or rectangles, for a hull measured as a box (`box`)
// - centred on (x, y) inches and turned `rotation` degrees clockwise. Overlap
// is checked as the backend checks it (see app/services/in_game/deployment.py):
// touching is fine.

const TOLERANCE = 1e-6
// Points round an oval base's edge, for checking it against another - as many
// as the backend checks (app/services/in_game/deployment.py), so a spot
// that's clear here is clear there.
const OUTLINE_POINTS = 48

// A point in the base's own frame, scaled so the base is a unit circle.
function toUnitCircle(px, py, base) {
  const angle = (-(base.rotation ?? 0) * Math.PI) / 180
  const dx = px - base.x
  const dy = py - base.y
  const u = dx * Math.cos(angle) - dy * Math.sin(angle)
  const v = dx * Math.sin(angle) + dy * Math.cos(angle)
  return [u / base.rx, v / base.ry]
}

function strictlyInside(px, py, base) {
  const [u, v] = toUnitCircle(px, py, base)
  if (base.box) return Math.max(Math.abs(u), Math.abs(v)) < 1 - TOLERANCE
  return Math.hypot(u, v) < 1 - TOLERANCE
}

function outline(base) {
  const angle = ((base.rotation ?? 0) * Math.PI) / 180
  const points = []
  if (base.box) {
    // Its corners and points along each side.
    const corners = [
      [-base.rx, -base.ry],
      [base.rx, -base.ry],
      [base.rx, base.ry],
      [-base.rx, base.ry],
    ]
    const perSide = OUTLINE_POINTS / 4
    corners.forEach(([u0, v0], i) => {
      const [u1, v1] = corners[(i + 1) % 4]
      for (let j = 0; j < perSide; j++) {
        const u = u0 + ((u1 - u0) * j) / perSide
        const v = v0 + ((v1 - v0) * j) / perSide
        points.push([
          base.x + u * Math.cos(angle) - v * Math.sin(angle),
          base.y + u * Math.sin(angle) + v * Math.cos(angle),
        ])
      }
    })
    return points
  }
  for (let i = 0; i < OUTLINE_POINTS; i++) {
    const t = (2 * Math.PI * i) / OUTLINE_POINTS
    const u = base.rx * Math.cos(t)
    const v = base.ry * Math.sin(t)
    points.push([
      base.x + u * Math.cos(angle) - v * Math.sin(angle),
      base.y + u * Math.sin(angle) + v * Math.cos(angle),
    ])
  }
  return points
}

export function basesOverlap(a, b) {
  if (a.rx === a.ry && b.rx === b.ry && !a.box && !b.box) {
    return Math.hypot(a.x - b.x, a.y - b.y) < a.rx + b.rx - TOLERANCE
  }
  return (
    strictlyInside(a.x, a.y, b) ||
    strictlyInside(b.x, b.y, a) ||
    outline(a).some(([x, y]) => strictlyInside(x, y, b)) ||
    outline(b).some(([x, y]) => strictlyInside(x, y, a))
  )
}

// How far a base's edge is from its centre at most (a box's corner).
function reachOf(base) {
  return base.box ? Math.hypot(base.rx, base.ry) : Math.max(base.rx, base.ry)
}

// Where a base being dragged to (x, y) can go without overlapping any of
// `others`: pushed out from whatever it lands on to just touching it (along
// the line from that base's centre), a few times over for crowded spots, and
// kept within `limit` ((x, y) => [x, y], e.g. its movement ring) - or, if
// that doesn't find a free spot, null.
export function freeSpot(base, x, y, others, limit = (px, py) => [px, py]) {
  let [cx, cy] = limit(x, y)
  for (let attempt = 0; attempt < 6; attempt++) {
    const hit = others.find((o) => basesOverlap({ ...base, x: cx, y: cy }, o))
    if (!hit) return [cx, cy]
    let dx = cx - hit.x
    let dy = cy - hit.y
    const length = Math.hypot(dx, dy)
    if (length < TOLERANCE) {
      dx = 1
      dy = 0
    } else {
      dx /= length
      dy /= length
    }
    // The nearest distance from its centre along that line that's clear of
    // it: between where it is and fully past both bases.
    let near = length
    let far = reachOf(hit) + reachOf(base) + 0.01
    if (far <= near) far = near + 0.01
    for (let i = 0; i < 25; i++) {
      const mid = (near + far) / 2
      const spot = { ...base, x: hit.x + dx * mid, y: hit.y + dy * mid }
      if (basesOverlap(spot, hit)) near = mid
      else far = mid
    }
    ;[cx, cy] = limit(hit.x + dx * far, hit.y + dy * far)
  }
  return others.some((o) => basesOverlap({ ...base, x: cx, y: cy }, o)) ? null : [cx, cy]
}

// How far a base can slide from (fromX, fromY) towards (toX, toY) before it
// would overlap one of `others` (or leave `limit`): the last clear spot on
// the way, just short of the first base it'd hit.
export function slide(base, fromX, fromY, toX, toY, others, limit = (px, py) => [px, py]) {
  const at = (t) => limit(fromX + (toX - fromX) * t, fromY + (toY - fromY) * t)
  const clear = (t) => {
    const [x, y] = at(t)
    return !others.some((o) => basesOverlap({ ...base, x, y }, o))
  }
  const steps = 40
  let last = 0
  for (let i = 1; i <= steps; i++) {
    if (!clear(i / steps)) {
      // Narrow down where it first touches, between the last clear step and
      // this one.
      let near = last
      let far = i / steps
      for (let j = 0; j < 20; j++) {
        const mid = (near + far) / 2
        if (clear(mid)) near = mid
        else far = mid
      }
      return at(near)
    }
    last = i / steps
  }
  return at(1)
}
