import { useEffect, useRef } from 'react'

// Asks to confirm an action (e.g. a delete) in a native <dialog> modal. Open
// while `open` is true; Escape or Cancel calls onCancel.
function ConfirmDialog({ open, title, message, confirmLabel = 'Delete', onConfirm, onCancel }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={dialogRef} className="app-dialog" onClose={onCancel}>
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault()
          onConfirm()
        }}
      >
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="inline-controls">
          <button type="submit">{confirmLabel}</button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </dialog>
  )
}

export default ConfirmDialog
