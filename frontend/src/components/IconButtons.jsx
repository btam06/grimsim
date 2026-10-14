import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCopy, faPencil, faXmark } from '@fortawesome/free-solid-svg-icons'

// Icon-only action buttons used across list items. The label is kept as the
// button's tooltip and accessible name, so it still reads as "Edit" etc.
function IconButton({ icon, label, variant, onClick }) {
  return (
    <button
      type="button"
      className={`icon-button icon-button--${variant}`}
      onClick={onClick}
      title={label}
      aria-label={label}
    >
      <FontAwesomeIcon icon={icon} />
    </button>
  )
}

export function EditButton({ onClick }) {
  return <IconButton icon={faPencil} label="Edit" variant="edit" onClick={onClick} />
}

export function CopyButton({ onClick }) {
  return <IconButton icon={faCopy} label="Copy" variant="copy" onClick={onClick} />
}

export function DeleteButton({ onClick }) {
  return <IconButton icon={faXmark} label="Delete" variant="delete" onClick={onClick} />
}
