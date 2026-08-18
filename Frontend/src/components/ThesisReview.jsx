import { useState, useEffect } from "react"
import { apiFetch } from "../api"
import { IconBolt } from "@tabler/icons-react"

// Unchanged in behavior, restyled with .conviction-dots/.dot instead of
// inline style objects per-dot.
function ConvictionDots({ score }) {
  return (
    <span className="conviction-dots">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`dot${i <= score ? " filled" : ""}`} />
      ))}
    </span>
  )
}

function getDueStatus(reviewDate) {
  const today = new Date()
  const due = new Date(reviewDate)
  today.setHours(0, 0, 0, 0)
  due.setHours(0, 0, 0, 0)

  const diffDays = Math.round((today - due) / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return { text: "Due today", pillClass: "pill-warning" }
  if (diffDays > 0) return { text: `${diffDays} day${diffDays === 1 ? "" : "s"} overdue`, pillClass: "pill-danger" }
  return { text: "Not yet due", pillClass: "pill-muted" }
}

function ThesisReview() {
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submittingId, setSubmittingId] = useState(null)
  const [recentReviews, setRecentReviews] = useState([])
  const [recentRefreshKey, setRecentRefreshKey] = useState(0)

  // NEW — one optional notes draft per pending trade, keyed by trade id.
  // A plain object instead of separate useState calls because the number
  // of pending reviews is dynamic (however many trades are due), so there's
  // no fixed set of fields to declare ahead of time the way TradeForm can.
  const [notesDraft, setNotesDraft] = useState({})

  useEffect(() => {
    apiFetch("/thesis-reviews")
      .then((response) => {
        if (!response.ok) throw new Error("Thesis review endpoint not available yet")
        return response.json()
      })
      .then((data) => {
        setReviews(data.reviews)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    apiFetch("/thesis-reviews/recent")
      .then((response) => {
        if (!response.ok) throw new Error("not available")
        return response.json()
      })
      .then((data) => setRecentReviews(data.reviews))
      .catch(() => setRecentReviews([]))
  }, [recentRefreshKey])

  async function handleOutcome(tradeId, outcome) {
    setSubmittingId(tradeId)
    try {
      const response = await apiFetch(`/trades/${tradeId}/outcome`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        // review_notes is optional on the backend (nullable column) — send
        // whatever's in the draft, or null if the user left it blank. Never
        // send an empty string; null is the unambiguous "no note" value.
        body: JSON.stringify({
          outcome_tag: outcome,
          review_notes: notesDraft[tradeId]?.trim() || null,
        }),
      })
      if (!response.ok) throw new Error("Failed to save outcome")

      setReviews((prev) => prev.filter((r) => r.id !== tradeId))
      setNotesDraft((prev) => {
        const next = { ...prev }
        delete next[tradeId]
        return next
      })
      setRecentRefreshKey((prev) => prev + 1)
    } catch (err) {
      alert(`Couldn't save outcome: ${err.message}`)
    } finally {
      setSubmittingId(null)
    }
  }

  if (loading) return <p style={{ color: "var(--color-text-secondary)" }}>Loading thesis reviews...</p>
  if (error) return <p style={{ color: "var(--color-danger)" }}>Thesis review unavailable: {error}</p>

  const topbar = (
    <div className="topbar">
      <div>
        <h1>Thesis review</h1>
        <div className="sub">Grade past theses to build your accuracy record</div>
      </div>
    </div>
  )

  return (
    <>
      {topbar}
      <div className="content">
        {reviews.length === 0 ? (
          <p style={{ color: "var(--color-text-secondary)" }}>Nothing due for review yet.</p>
        ) : (
          <>
            <div className="section-title">
              Due now ({reviews.length})
            </div>

            {reviews.map((r) => {
              const due = getDueStatus(r.review_date)
              const isSubmitting = submittingId === r.id

              return (
                <div key={r.id} className="review-card">
                  <div className="review-top">
                    <div className="review-ticker">
                      <div className="ticker-badge">{r.ticker.slice(0, 2)}</div>
                      <div>
                        <span className="ticker-name">{r.ticker}</span>
                        <span className="pill pill-muted" style={{ marginLeft: "6px" }}>{r.action}</span>
                      </div>
                    </div>
                    <span className={`pill ${due.pillClass}`}>{due.text}</span>
                  </div>

                  <div className="thesis-quote">"{r.thesis_text}"</div>

                  <div className="review-meta">
                    <span>Conviction</span>
                    <ConvictionDots score={r.conviction_score} />
                    <span>Traded {r.trade_date}</span>
                  </div>

                  {r.fomo_flag && (
                    <div className="fomo-line">
                      <IconBolt size={13} /> {r.fomo_reason}
                    </div>
                  )}

                  {/* NEW — optional reflection notes, saved alongside whichever
                      grade button gets clicked. Reuses .field/.field textarea
                      from theme.css (same serif treatment as the trade thesis
                      textarea) rather than inventing a new input style — this
                      is the same kind of reflective content, just written
                      after the fact instead of at trade time. */}
                  <div className="field" style={{ marginTop: "var(--space-md)", marginBottom: 0 }}>
                    <label>Notes (optional) — what were you thinking? What actually happened?</label>
                    <textarea
                      value={notesDraft[r.id] || ""}
                      onChange={(e) => setNotesDraft((prev) => ({ ...prev, [r.id]: e.target.value }))}
                      placeholder="e.g. Held longer than planned because earnings got pushed back a week..."
                      style={{ minHeight: "70px" }}
                    />
                  </div>

                  <div className="grade-row">
                    {["correct", "incorrect", "mixed"].map((outcome) => (
                      <button
                        key={outcome}
                        disabled={isSubmitting}
                        onClick={() => handleOutcome(r.id, outcome)}
                        className={`grade-btn ${outcome}`}
                      >
                        {outcome.charAt(0).toUpperCase() + outcome.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </>
        )}

        {recentReviews.length > 0 && (
          <>
            <div className="section-title">Recently reviewed</div>
            <div className="card" style={{ padding: "0 var(--space-lg)" }}>
              {recentReviews.map((r) => {
                const pillClass =
                  r.outcome_tag === "correct" ? "pill-success" :
                  r.outcome_tag === "incorrect" ? "pill-danger" :
                  "pill-warning"

                return (
                  <div key={r.id} className="recent-row">
                    <div>
                      <span className="ticker-name">{r.ticker}</span>{" "}
                      <span style={{ color: "var(--color-text-muted)" }}>"{r.thesis_text}"</span>
                      {/* NEW — shows the saved note, if one was left, so
                          "what was I thinking" is answerable at a glance
                          without re-opening the original trade. */}
                      {r.review_notes && <div className="recent-note">{r.review_notes}</div>}
                    </div>
                    <span className={`pill ${pillClass}`}>{r.outcome_tag}</span>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {reviews.length === 0 && recentReviews.length === 0 && (
          <p style={{ color: "var(--color-text-secondary)" }}>
            No theses reviewed yet — grade one once its review date arrives.
          </p>
        )}
      </div>
    </>
  )
}

export default ThesisReview
