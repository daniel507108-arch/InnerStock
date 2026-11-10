import { useState, useEffect, useRef } from "react"
import { LineChart, Line, ResponsiveContainer, ReferenceLine, XAxis, YAxis, Tooltip } from "recharts"
import { apiFetch } from "../api"
import { IconBolt, IconScale } from "@tabler/icons-react"

const OUTCOMES = ["correct", "incorrect", "mixed"]

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

function formatDate(isoDate) {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

function formatPct(value) {
  if (value === null || value === undefined) return "—"
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`
}

function toneOf(value) {
  if (value === null || value === undefined || value === 0) return ""
  return value > 0 ? " positive" : " negative"
}

// "correct" vs "incorrect" is a flat contradiction; "mixed" never is.
// Same rule as grading.contradicts on the backend, which enforces it.
function contradicts(suggested, outcome) {
  return suggested && suggested !== outcome && suggested !== "mixed" && outcome !== "mixed"
}

// The evidence block: what the price did, what the S&P 500 did over the
// same days, and a small chart since the trade. Numbers are measured at
// the review date the user picked when they wrote the thesis (so waiting
// for a bounce before grading doesn't help), with today's number as context.
function Scorecard({ card, action }) {
  if (!card.available) {
    return <div className="score-empty">{card.message}</div>
  }

  const sinceLabel = action === "buy" ? "Since you bought" : "Since you sold"
  const whenLabel = card.judged_at === "review_date" ? `at your review date (${formatDate(card.at_review.date)})` : "so far"
  const benchmark = card.benchmark?.label

  return (
    <div className="scorecard">
      <div className="score-grid">
        <div className="score-stat">
          <span className="score-label">{sinceLabel}, {whenLabel}</span>
          <span className={`score-value${toneOf(card.return_pct)}`}>{formatPct(card.return_pct)}</span>
        </div>
        {benchmark && (
          <>
            <div className="score-stat">
              <span className="score-label">{benchmark} over the same days</span>
              <span className={`score-value${toneOf(card.benchmark_return_pct)}`}>{formatPct(card.benchmark_return_pct)}</span>
            </div>
            <div className="score-stat">
              <span className="score-label">{action === "buy" ? "You vs. the market" : "Stock vs. the market"}</span>
              <span className={`score-value${toneOf(card.excess_pct)}`}>
                {card.excess_pct === null ? "—" : `${card.excess_pct > 0 ? "+" : ""}${card.excess_pct.toFixed(1)} pts`}
              </span>
            </div>
          </>
        )}
      </div>

      <div className="score-chart">
        <ResponsiveContainer width="100%" height={110}>
          <LineChart data={card.series} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              formatter={(value) => [`$${Number(value).toFixed(2)}`, card.ticker]}
              labelFormatter={(label) => formatDate(label)}
              contentStyle={{ background: "var(--color-surface-alt)", border: "1px solid var(--color-border)", fontSize: 12 }}
            />
            <ReferenceLine y={card.entry_price} stroke="var(--color-text-muted)" strokeDasharray="4 4" />
            {card.at_review && <ReferenceLine x={card.at_review.date} stroke="var(--color-accent)" strokeDasharray="2 3" />}
            <Line type="monotone" dataKey="close" stroke="var(--color-text-primary)" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
        <div className="score-chart-legend">
          <span>- - your {action === "buy" ? "buy" : "sale"} price ${card.entry_price.toFixed(2)}</span>
          {card.at_review && <span className="accent">┊ review date</span>}
          <span>Best {formatPct(card.best_pct)} · Worst {formatPct(card.worst_pct)}</span>
          {card.judged_at === "review_date" && <span>Today {formatPct(card.return_now_pct)}</span>}
        </div>
      </div>
      {card.split_adjusted && <div className="score-note">Adjusted for a stock split since the trade.</div>}
    </div>
  )
}

function ReviewCard({ review, onGraded }) {
  const [card, setCard] = useState(null)
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const notesRef = useRef(null)

  useEffect(() => {
    apiFetch(`/thesis-reviews/${review.id}/scorecard`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setCard)
      .catch(() => setCard({ available: false, message: "Couldn't load prices - grade it from memory." }))
  }, [review.id])

  const suggested = card?.suggestion?.outcome
  const due = getDueStatus(review.review_date)
  const needsNoteFor = (outcome) => contradicts(suggested, outcome) && !notes.trim()

  async function handleOutcome(outcome) {
    if (needsNoteFor(outcome)) {
      setError(`The numbers say "${suggested}". If you still think it was ${outcome}, write down why first.`)
      notesRef.current?.focus()
      return
    }
    setSaving(true)
    setError(null)
    try {
      const response = await apiFetch(`/trades/${review.id}/outcome`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome_tag: outcome, review_notes: notes.trim() || null }),
      })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.detail || "Couldn't save the grade")
      onGraded(review.id)
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <div className="review-card">
      <div className="review-top">
        <div className="review-ticker">
          <div className="ticker-badge">{review.ticker.slice(0, 2)}</div>
          <div>
            <span className="ticker-name">{review.ticker}</span>
            <span className={`pill ${review.action === "buy" ? "pill-success" : "pill-danger"}`} style={{ marginLeft: "6px" }}>
              {review.action}
            </span>
          </div>
        </div>
        <span className={`pill ${due.pillClass}`}>{due.text}</span>
      </div>

      {/* What the user said at the time - the claim being graded. */}
      {review.reasons.length > 0 && (
        <div className="reason-tags">
          {review.reasons.map((r) => <span key={r.tag} className="reason-tag">{r.label}</span>)}
          {review.written_in_hindsight && <span className="reason-tag hindsight">written in hindsight</span>}
        </div>
      )}
      {review.thesis_text && <div className="thesis-quote">"{review.thesis_text}"</div>}

      <div className="review-meta">
        <span>Conviction</span>
        {review.conviction_score ? <ConvictionDots score={review.conviction_score} /> : <span>—</span>}
        <span>
          {review.action === "buy" ? "Bought" : "Sold"} {review.quantity.toLocaleString(undefined, { maximumFractionDigits: 4 })} @ $
          {review.price_per_share.toFixed(2)} on {formatDate(review.trade_date)}
        </span>
      </div>

      {/* What actually happened. */}
      {card ? <Scorecard card={card} action={review.action} /> : <div className="score-empty">Loading prices…</div>}

      {card?.fomo?.fomo_flag && (
        <div className="fomo-line">
          <IconBolt size={13} /> {card.fomo.reason}
        </div>
      )}

      {card?.suggestion && (
        <div className={`score-suggestion ${suggested}`}>
          <IconScale size={15} />
          <span>
            The numbers say <strong>{suggested}</strong>: {card.suggestion.reason}
          </span>
        </div>
      )}
      {card?.suggestion_note && <div className="score-note">{card.suggestion_note}</div>}

      <div className="field" style={{ marginTop: "var(--space-md)", marginBottom: 0 }}>
        <label>Notes — what happened, and what would you do differently? (required if you disagree with the numbers)</label>
        <textarea
          ref={notesRef}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g. Earnings were fine but the whole sector sold off - thesis still intact, timing was wrong."
          style={{ minHeight: "70px" }}
        />
      </div>

      {error && <div className="brokerage-message error">{error}</div>}

      <div className="grade-row">
        {OUTCOMES.map((outcome) => (
          <button
            key={outcome}
            disabled={saving || !card}
            onClick={() => handleOutcome(outcome)}
            className={`grade-btn ${outcome}${suggested === outcome ? " suggested" : ""}`}
            title={suggested === outcome ? "What the numbers suggest" : undefined}
          >
            {outcome.charAt(0).toUpperCase() + outcome.slice(1)}
            {suggested === outcome && <span className="grade-btn-hint">suggested</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

function ThesisReview() {
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [recentReviews, setRecentReviews] = useState([])
  const [recentRefreshKey, setRecentRefreshKey] = useState(0)

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

  function handleGraded(tradeId) {
    setReviews((prev) => prev.filter((r) => r.id !== tradeId))
    setRecentRefreshKey((prev) => prev + 1)
  }

  if (loading) return <p style={{ color: "var(--color-text-secondary)" }}>Loading thesis reviews...</p>
  if (error) return <p style={{ color: "var(--color-danger)" }}>Thesis review unavailable: {error}</p>

  const topbar = (
    <div className="topbar">
      <div>
        <h1>Thesis review</h1>
        <div className="sub">Grade past theses against what actually happened</div>
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
            <div className="section-title">Due now ({reviews.length})</div>
            {reviews.map((r) => <ReviewCard key={r.id} review={r} onGraded={handleGraded} />)}
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
                      <span style={{ color: "var(--color-text-muted)" }}>
                        {r.thesis_text ? `"${r.thesis_text}"` : r.reasons.map((x) => x.label).join(", ")}
                      </span>
                      {r.graded_return_pct !== null && (
                        <div className="recent-numbers">
                          <span className={toneOf(r.graded_return_pct).trim()}>{formatPct(r.graded_return_pct)}</span>
                          {r.graded_benchmark_return_pct !== null && <> vs S&amp;P 500 {formatPct(r.graded_benchmark_return_pct)}</>}
                        </div>
                      )}
                      {/* Shows the saved note, if one was left, so "what
                          was I thinking" is answerable at a glance. */}
                      {r.review_notes && <div className="recent-note">{r.review_notes}</div>}
                    </div>
                    <div className="recent-pills">
                      <span className={`pill ${pillClass}`}>{r.outcome_tag}</span>
                      {r.graded_against_numbers && (
                        <span className="pill pill-muted" title={`The numbers said ${r.suggested_outcome}`}>against the numbers</span>
                      )}
                    </div>
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
