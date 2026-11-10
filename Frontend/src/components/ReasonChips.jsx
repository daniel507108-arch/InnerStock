// Tappable reason chips ("Bought the dip", "Tip / social media", ...) used by
// both the Log Trade form and the Trade Reasons inbox. The list itself comes
// from GET /trades/reasons, so the backend's catalog (thesis.py) is the one
// source of truth for which reasons exist.
//
// "Don't remember" is exclusive: picking it clears the other reasons, and
// picking any other reason clears it - the backend rejects the combination.
import { DONT_REMEMBER } from "../reasons"

function ReasonChips({ options, selected, onChange, includeDontRemember = true }) {
  function toggle(tag) {
    if (selected.includes(tag)) {
      onChange(selected.filter((t) => t !== tag))
    } else if (tag === DONT_REMEMBER) {
      onChange([DONT_REMEMBER])
    } else {
      onChange([...selected.filter((t) => t !== DONT_REMEMBER), tag])
    }
  }

  return (
    <div className="reason-chips">
      {options
        .filter((o) => includeDontRemember || o.tag !== DONT_REMEMBER)
        .map((option) => (
          <button
            key={option.tag}
            type="button"
            className={`reason-chip${selected.includes(option.tag) ? " selected" : ""}${
              option.tag === DONT_REMEMBER ? " muted" : ""
            }`}
            aria-pressed={selected.includes(option.tag)}
            onClick={() => toggle(option.tag)}
          >
            {option.label}
          </button>
        ))}
    </div>
  )
}

export default ReasonChips
