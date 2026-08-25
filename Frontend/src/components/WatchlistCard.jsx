import { useState, useEffect } from "react"
import { apiFetch } from "../api"

function WatchlistCard({ refreshKey }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    apiFetch("/watchlist")
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load watchlist")
        return response.json()
      })
      .then((result) => {
        setItems(result.watchlist || [])
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [refreshKey])

  async function handleRemove(ticker) {
    const previous = items
    setItems(items.filter((i) => i.ticker !== ticker)) // optimistic — remove now, roll back on failure

    try {
      const response = await apiFetch(`/watchlist/${ticker}`, { method: "DELETE" })
      if (!response.ok) throw new Error("Failed to remove")
    } catch {
      setItems(previous)
    }
  }

  return (
    <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "var(--space-lg)" }}>
      <div style={{ fontWeight: 500, fontSize: "var(--text-md)", marginBottom: "12px" }}>Watchlist</div>

      {loading && <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>Loading watchlist...</p>}
      {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>
          No tickers on your watchlist yet. Add one from the Search tab.
        </p>
      )}

      {!loading && !error && items.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {items.map((item) => (
            <div key={item.ticker} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0" }}>
              <span style={{ fontWeight: 500, width: "80px" }}>{item.ticker}</span>
              <span style={{ width: "80px" }}>{item.current_price != null ? `$${item.current_price.toFixed(2)}` : "—"}</span>
              <span style={{ width: "80px", color: (item.day_change_percent ?? 0) >= 0 ? "var(--color-success)" : "var(--color-danger)" }}>
                {item.day_change_percent != null ? `${item.day_change_percent >= 0 ? "+" : ""}${item.day_change_percent.toFixed(2)}%` : "—"}
              </span>
              <button
                onClick={() => handleRemove(item.ticker)}
                style={{ background: "transparent", border: "none", color: "var(--color-text-secondary)", cursor: "pointer", fontSize: "var(--text-md)" }}
                aria-label={`Remove ${item.ticker} from watchlist`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default WatchlistCard