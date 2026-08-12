import { useState, useEffect } from "react"
import { apiFetch } from "../api"

function SentimentBadge({ ticker }) {
  const [sentiment, setSentiment] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    setLoading(true)
    setUnavailable(false)

    apiFetch(`/sentiment/${ticker}`)
      .then(response => {
        if (!response.ok) throw new Error("not available")
        return response.json()
      })
      .then(data => {
        setSentiment(data.sentiment)
        setSummary(data.summary)
        setLoading(false)
      })
      .catch(() => {
        setUnavailable(true)
        setLoading(false)
      })
  }, [ticker])

  if (loading) return <span className="sentiment-badge sentiment-loading">…</span>
  if (unavailable) return <span className="sentiment-badge sentiment-unavailable">—</span>

  const colorClass =
    sentiment === "positive" ? "sentiment-positive" :
    sentiment === "negative" ? "sentiment-negative" :
    "sentiment-neutral"

  return (
    <span className={`sentiment-badge ${colorClass}`} title={summary || "No summary available"}>
      {sentiment}
    </span>
  )
}

export default SentimentBadge