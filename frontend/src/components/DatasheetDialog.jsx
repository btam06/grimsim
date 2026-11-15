import { useEffect, useRef } from 'react'
import { RemoveButton } from './IconButtons'
import { DatasheetContent } from './UnitDatasheet'

// A unit's datasheet (see UnitDatasheet) in a native <dialog> modal, open
// while `unit` is set, followed by any units attached to it ({ unit, title }). Escape, the close button or a click on the backdrop
// calls onClose.
function DatasheetDialog({ unit, title, data, attached = [], onClose }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (unit && !dialog.open) dialog.showModal()
    if (!unit && dialog.open) dialog.close()
  }, [unit])

  return (
    <dialog
      ref={dialogRef}
      className="app-dialog app-dialog--wide"
      onClose={onClose}
      // (A click on the backdrop lands on the dialog itself.)
      onClick={(e) => e.target === dialogRef.current && onClose()}
    >
      {unit && (
        <>
          <div className="dialog-header">
            <h3>{title}</h3>
            <RemoveButton label="Close" onClick={onClose} />
          </div>
          <DatasheetContent unit={unit} data={data} showBases={false} />
          {attached.map((a) => (
            <div key={a.unit.id} className="datasheet-attached">
              <h3>{a.title}</h3>
              <DatasheetContent unit={a.unit} data={data} showBases={false} />
            </div>
          ))}
        </>
      )}
    </dialog>
  )
}

export default DatasheetDialog
