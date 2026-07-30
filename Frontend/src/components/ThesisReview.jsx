import { useState, useEffect } from "react"

function ThesisReview() {
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Tracks which specific trade is mid-submit, so we can disable just
  // that row's buttons instead of freezing the whole list.
  const [submittingId, setSubmittingId] = useState(null)

  useEffect(() => {
    fetch("http://127.0.0.1:8000/thesis-reviews")
      .then(response => {
        if (!response.ok) throw new Error("Thesis review endpoint not available yet")
        return response.json()
      })
      .then(data => {
        setReviews(data.reviews)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  async function handleOutcome(tradeId, outcome) {
    setSubmittingId(tradeId)
    try {
      const response = await fetch(`http://127.0.0.1:8000/trades/${tradeId}/outcome`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome_tag: outcome }),
      })
      if (!response.ok) throw new Error("Failed to save outcome")

      // Remove this trade from the visible list — it's been reviewed,
      // no need to re-fetch the whole list just to drop one item.
      setReviews((prev) => prev.filter((r) => r.id !== tradeId))
    } catch (err) {
      alert(`Couldn't save outcome: ${err.message}`) // simple, temporary feedback
    } finally {
      setSubmittingId(null)
    }
  }

  if (loading) return <p style={{ color: "var(--color-text-secondary)" }}>Loading thesis reviews...</p>
if (error) return <p style={{ color: "var(--color-danger)" }}>Thesis review unavailable: {error}</p>
if (reviews.length === 0) return <p style={{ color: "var(--color-text-secondary)" }}>Nothing due for review yet.</p>

  return (
    <div style={{ background: "var(--color-surface)", padding: "16px", borderRadius: "var(--radius-md)" }}>
      <h3 style={{ marginTop: 0, color: "var(--color-text-primary)" }}>Thesis review</h3>
      {reviews.map((r) => (
        <div key={r.id} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", padding: "1rem", marginBottom: "1rem", background: "var(--color-surface-alt)" }}>
          <strong style={{ color: "var(--color-text-primary)" }}>{r.ticker}</strong>
          <span style={{ color: "var(--color-text-secondary)" }}> — {r.action} on {r.trade_date}</span>
          <p style={{ fontStyle: "italic", color: "var(--color-text-primary)" }}>"{r.thesis_text}"</p>
          <p style={{ color: "var(--color-text-secondary)" }}>Conviction at the time: {r.conviction_score}/5</p>
          {r.fomo_flag && (
  <p style={{ color: "var(--color-warning)", fontSize: "0.85rem" }}>⚡ This entry followed a sharp price run-up — possible FOMO buy</p>
)}

          <button disabled={submittingId === r.id} onClick={() => handleOutcome(r.id, "correct")}>
            Correct
          </button>
          <button disabled={submittingId === r.id} onClick={() => handleOutcome(r.id, "incorrect")}>
            Incorrect
          </button>
          <button disabled={submittingId === r.id} onClick={() => handleOutcome(r.id, "mixed")}>
            Mixed
          </button>
        </div>
      ))}
    </div>
  )
}

export default ThesisReview