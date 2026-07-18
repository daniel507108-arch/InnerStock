import { useState, useEffect } from "react"

// This component gets reused once per holding — HoldingsTable renders
// several of these, each one receiving a different "ticker" via props.
function SentimentBadge({ ticker }) {
  const [sentiment, setSentiment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    setLoading(true)
    setUnavailable(false)

    fetch(`http://127.0.0.1:8000/sentiment/${ticker}`)
      .then(response => {
        if (!response.ok) throw new Error("not available")
        return response.json()
      })
      .then(data => {
        setSentiment(data.sentiment)
        setLoading(false)
      })
      .catch(() => {
        // Decorative feature, not core — fail quietly instead of a red error.
        setUnavailable(true)
        setLoading(false)
      })
  }, [ticker]) // re-run specifically when THIS badge's ticker changes

  if (loading) return <span className="sentiment-badge sentiment-loading">…</span>
  if (unavailable) return <span className="sentiment-badge sentiment-unavailable">—</span>

  // Chained ternary: check positive first, then negative, otherwise assume neutral.
  const colorClass =
    sentiment === "positive" ? "sentiment-positive" :
    sentiment === "negative" ? "sentiment-negative" :
    "sentiment-neutral"

  return <span className={`sentiment-badge ${colorClass}`}>{sentiment}</span>
}

export default SentimentBadge