import { useEffect, useRef, useState } from 'react'
import {
  listBaseSizes,
  listDatasheetAbilities,
  listFactionAbilities,
  listKeywords,
  listWeaponAbilities,
} from '../api'
import { RemoveButton } from './IconButtons'
import { DatasheetContent } from './UnitDatasheet'

// What a datasheet needs besides the unit's models, weapons and wargear -
// fetched the first time one is opened, then kept.
let lookups = null
const loadLookups = () => {
  lookups ??= Promise.all([
    listWeaponAbilities(),
    listDatasheetAbilities(),
    listFactionAbilities(),
    listBaseSizes(),
    listKeywords(),
  ]).then(([weaponAbilities, datasheetAbilities, factionAbilities, baseSizes, keywords]) => ({
    weaponAbilities,
    datasheetAbilities,
    factionAbilities,
    baseSizes,
    keywords,
  }))
  // (A failed fetch is tried again next time.)
  lookups.catch(() => {
    lookups = null
  })
  return lookups
}

// The units' bases: each kind of model's, named by the model when they
// differ.
function basesOf(units, models, baseSizes) {
  const byModel = new Map()
  units
    .flatMap((u) => u.unit_models)
    .forEach((um) => {
      const model = models.find((m) => m.id === um.model_id)
      const base = baseSizes.find((b) => b.id === model?.base_size_id)
      if (base) byModel.set(model.name, base.name)
    })
  const bases = [...new Set(byModel.values())]
  if (bases.length <= 1) return bases.length ? `${bases[0]} base` : ''
  return [...byModel].map(([model, base]) => `${model} (${base} base)`).join(', ')
}

// A unit's datasheet (see UnitDatasheet) in a native <dialog> modal, open
// while `unit` is set, followed by any units attached to it ({ unit, title }).
// `title` is shown with the units' bases; `data` is the models, weapons,
// wargear and enhancements; `empty` is shown for a unit with no models yet.
// Escape, the close button or a click on the backdrop calls onClose.
function DatasheetDialog({ unit, title, data, attached = [], empty, onClose }) {
  const dialogRef = useRef(null)
  const [loaded, setLoaded] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!unit || loaded) return
    loadLookups()
      .then(setLoaded)
      .catch((err) => setError(err.message))
  }, [unit, loaded])

  const open = Boolean(unit && (loaded || error))
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const full = loaded && { ...data, ...loaded }
  const bases =
    open && full ? basesOf([unit, ...attached.map((a) => a.unit)], data.models, full.baseSizes) : ''

  return (
    <dialog
      ref={dialogRef}
      className="app-dialog app-dialog--wide"
      onClose={onClose}
      // (A click on the backdrop lands on the dialog itself.)
      onClick={(e) => e.target === dialogRef.current && onClose()}
    >
      {open && (
        <>
          <div className="dialog-header">
            <h3>
              {title}
              {bases && ` · ${bases}`}
            </h3>
            <RemoveButton label="Close" onClick={onClose} />
          </div>
          {error && <p className="error">{error}</p>}
          {full && unit.unit_models.length === 0 && empty && <p className="hint">{empty}</p>}
          {full && <DatasheetContent unit={unit} data={full} showBases={false} />}
          {full &&
            attached.map((a) => (
              <div key={a.unit.id} className="datasheet-attached">
                <h3>{a.title}</h3>
                <DatasheetContent unit={a.unit} data={full} showBases={false} />
              </div>
            ))}
        </>
      )}
    </dialog>
  )
}

export default DatasheetDialog
