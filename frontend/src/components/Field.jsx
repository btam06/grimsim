function Field({ label, children }) {
  return (
    <label className="input-field">
      {label}
      {children}
    </label>
  )
}

export default Field
