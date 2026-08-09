import { useState, useEffect } from "react"
import { IconBolt, IconClock } from "@tabler/icons-react"
import { apiFetch } from "../api"

function ConvictionDots({ score }) {
  return (
    <span style={{ display: "inline-flex", gap: "3px" }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            display: "inline-block",
            background: i <= score ? "var(--color-text-primary)" : "transparent",
            border: i <= score ? "none" : "1px solid var(--color-border-strong)",
          }}
        />
      ))}
    </span>
  )
}

function ThesisReview() {
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Tracks which specific trade is mid-submit, so we can disable just
  // that row's buttons instead of freezing the whole list.
  const [submittingId, setSubmittingId] = useState(null)
  const [recentReviews, setRecentReviews] = useState([])
  const [recentRefreshKey, setRecentRefreshKey] = useState(0)

  useEffect(() => {
    apiFetch("/thesis-reviews")
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

useEffect(() => {
  apiFetch("/thesis-reviews/recent")
    .then(response => {
      if (!response.ok) throw new Error("not available")
      return response.json()
    })
    .then(data => setRecentReviews(data.reviews))
    .catch(() => setRecentReviews([]))
}, [recentRefreshKey])

  async function handleOutcome(tradeId, outcome) {
    setSubmittingId(tradeId)
    try {
      const response = await apiFetch(`/trades/${tradeId}/outcome`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome_tag: outcome }),
      })
      if (!response.ok) throw new Error("Failed to save outcome")

      // Remove this trade from the visible list — it's been reviewed,
      // no need to re-fetch the whole list just to drop one item.
      setReviews((prev) => prev.filter((r) => r.id !== tradeId))
      setRecentRefreshKey((prev) => prev + 1)
    } catch (err) {
      alert(`Couldn't save outcome: ${err.message}`) // simple, temporary feedback
    } finally {
      setSubmittingId(null)
    }
  }

  if (loading) return <p style={{ color: "var(--color-text-secondary)" }}>Loading thesis reviews...</p>
if (error) return <p style={{ color: "var(--color-danger)" }}>Thesis review unavailable: {error}</p>
if (reviews.length === 0) return <p style={{ color: "var(--color-text-secondary)" }}>Nothing due for review yet.</p>

function getDueStatus(reviewDate) {
  const today = new Date()
  const due = new Date(reviewDate)
  today.setHours(0, 0, 0, 0)
  due.setHours(0, 0, 0, 0)

  const diffDays = Math.round((today - due) / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return { text: "Due today", color: "var(--color-warning)" }
  if (diffDays > 0) return { text: `${diffDays} day${diffDays === 1 ? "" : "s"} overdue`, color: "var(--color-danger)" }
  return { text: "Not yet due", color: "var(--color-text-secondary)" }
}

  return (
    <div style={{ background: "var(--color-surface)", padding: "16px", borderRadius: "var(--radius-md)" }}>
      <h3 style={{ marginTop: 0, marginBottom: "4px", fontSize: "var(--text-lg)", fontWeight: "var(--font-weight-medium)", color: "var(--color-text-primary)" }}>Thesis review</h3>
<p style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)", display: "flex", alignItems: "center", gap: "6px", marginBottom: "var(--space-md)" }}>
  <IconClock size={15} /> {reviews.length} thesis{reviews.length === 1 ? "" : "es"} due for review
</p>
      {reviews.map((r) => (
  <div key={r.id} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", padding: "var(--space-md)", marginBottom: "var(--space-md)", background: "var(--color-surface-alt)" }}>

    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <strong style={{ color: "var(--color-text-primary)", fontWeight: "var(--font-weight-medium)" }}>{r.ticker}</strong>
        <span style={{ background: "var(--color-surface)", color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", padding: "2px 8px", borderRadius: "999px", textTransform: "capitalize" }}>
          {r.action}
        </span>
      </div>
      <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>Traded {r.trade_date}</span>
    </div>

    <p style={{ fontStyle: "italic", color: "var(--color-text-primary)" }}>"{r.thesis_text}"</p>

    {r.fomo_flag && (
      <p style={{ color: "var(--color-warning)", fontSize: "var(--text-sm)", display: "flex", alignItems: "center", gap: "6px" }}>
        <IconBolt size={15} /> {r.fomo_reason}
      </p>
    )}

    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-sm)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>Conviction at the time</span>
        <ConvictionDots score={r.conviction_score} />
      </div>
      <span style={{ fontSize: "var(--text-sm)", color: getDueStatus(r.review_date).color }}>
        {getDueStatus(r.review_date).text}
      </span>
    </div>

    <div style={{ display: "flex", gap: "8px" }}>
      {["correct", "incorrect", "mixed"].map((outcome) => (
        <button
          key={outcome}
          disabled={submittingId === r.id}
          onClick={() => handleOutcome(r.id, outcome)}
          style={{ background: "transparent", color: "var(--color-text-primary)", border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-sm)", padding: "0.4rem 0.8rem", flex: 1, cursor: submittingId === r.id ? "default" : "pointer", opacity: submittingId === r.id ? 0.5 : 1 }}
        >
          {outcome.charAt(0).toUpperCase() + outcome.slice(1)}
        </button>
      ))}
    </div>
  </div>
))}

{recentReviews.length > 0 && (
  <div>
    <p style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)", marginBottom: "var(--space-sm)" }}>
      Recently reviewed
    </p>
    {recentReviews.map((r) => {
      const outcomeColor =
        r.outcome_tag === "correct" ? "var(--color-success)" :
        r.outcome_tag === "incorrect" ? "var(--color-danger)" :
        "var(--color-warning)"
      const outcomeBg =
        r.outcome_tag === "correct" ? "var(--color-success-bg)" :
        r.outcome_tag === "incorrect" ? "var(--color-danger-bg)" :
        "var(--color-warning-bg)"
      return (
        <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.6rem 0.8rem", borderRadius: "var(--radius-sm)", background: "var(--color-surface)", marginBottom: "0.4rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <strong style={{ fontSize: "var(--text-sm)" }}>{r.ticker}</strong>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>"{r.thesis_text}"</span>
          </div>
          <span style={{ background: outcomeBg, color: outcomeColor, fontSize: "var(--text-xs)", padding: "2px 8px", borderRadius: "999px", textTransform: "capitalize" }}>
            {r.outcome_tag}
          </span>
        </div>
      )
    })}
  </div>
)}

    </div>
  )
}

export default ThesisReview