import { useState, useEffect } from "react"
import { apiFetch } from "../api"

// Logic is untouched — only the className mapping changed, from the old
// component-local .sentiment-* classes (defined in HoldingsTable's <style>
// block) to the shared .pill / .pill-success / .pill-danger / .pill-muted
// classes now in theme.css. Same visual idea (colored capsule), now reusing
// the same pill system as the concentration banner's badges and the
// thesis-review outcome tags, instead of a fourth parallel color scheme.
function SentimentBadge({ ticker }) {
  const [sentiment, setSentiment] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    setLoading(true)
    setUnavailable(false)

    apiFetch(`/sentiment/${ticker}`)
      .then((response) => {
        if (!response.ok) throw new Error("not available")
        return response.json()
      })
      .then((data) => {
        setSentiment(data.sentiment)
        setSummary(data.summary)
        setLoading(false)
      })
      .catch(() => {
        setUnavailable(true)
        setLoading(false)
      })
  }, [ticker])

  if (loading) return <span className="pill pill-muted">…</span>
  if (unavailable) return <span className="pill pill-muted">—</span>

  const pillClass =
    sentiment === "positive" ? "pill-success" : sentiment === "negative" ? "pill-danger" : "pill-muted"

  return (
    <span className={`pill ${pillClass}`} title={summary || "No summary available"}>
      {sentiment}
    </span>
  )
}

export default SentimentBadge
