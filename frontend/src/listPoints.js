// A list's points: its units', plus their enhancements' and upgrades'.
export function listPoints(units, enhancements) {
  const enhancementPoints = (id) => enhancements.find((e) => e.id === id)?.points ?? 0
  return units.reduce(
    (sum, u) =>
      sum +
      u.points +
      (u.upgrade_id !== null ? enhancementPoints(u.upgrade_id) : 0) +
      u.unit_models.reduce(
        (s, m) => s + (m.enhancement_id !== null ? enhancementPoints(m.enhancement_id) : 0),
        0
      ),
    0
  )
}
