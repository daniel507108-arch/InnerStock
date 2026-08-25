import { useState, useEffect } from "react"
import { apiFetch } from "../api"

// Same interval as Dashboard.jsx's PRICE_POLL_INTERVAL_MS - this sidebar is
// visible on every tab, not just the Dashboard, so it needs its own poll
// rather than relying on the Dashboard's to keep it current.
const PRICE_POLL_INTERVAL_MS = 60_000

function SidebarWatchlist({ onNavigate }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  // isPoll mirrors the Dashboard's pattern: only the initial/triggered
  // fetch shows the loading state, background polls update quietly so the
  // list doesn't flicker empty every 60s.
  function fetchWatchlist(isPoll = false) {
    if (!isPoll) setLoading(true)
    apiFetch("/watchlist")
      .then((response) => (response.ok ? response.json() : { watchlist: [] }))
      .then((result) => setItems(result.watchlist || []))
      .catch(() => {
        if (!isPoll) setItems([])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    // Wrapped in arrow functions rather than passed directly - addEventListener
    // calls its handler with the DOM Event as the first argument, which would
    // otherwise land in fetchWatchlist's `isPoll` parameter and get treated as
    // a background poll instead of the deliberate refresh it actually is.
    const handleWatchlistUpdated = () => fetchWatchlist(false)
    handleWatchlistUpdated()
    window.addEventListener("watchlist-updated", handleWatchlistUpdated)
    const intervalId = setInterval(() => fetchWatchlist(true), PRICE_POLL_INTERVAL_MS)
    return () => {
      window.removeEventListener("watchlist-updated", handleWatchlistUpdated)
      clearInterval(intervalId)
    }
  }, [])

  async function handleRemove(ticker, e) {
    e.stopPropagation()
    const previous = items
    setItems(items.filter((i) => i.ticker !== ticker))
    try {
      const response = await apiFetch(`/watchlist/${ticker}`, { method: "DELETE" })
      if (!response.ok) throw new Error()
    } catch {
      setItems(previous)
    }
  }

  return (
    <div className="sidebar-watchlist">
      <div className="sidebar-watchlist-title">Watchlist</div>

      {!loading && items.length === 0 && (
        <div className="sidebar-watchlist-empty">Nothing tracked yet.</div>
      )}

      {items.map((item) => (
        <div key={item.ticker} className="sidebar-watchlist-row">
          <span className="sidebar-watchlist-ticker">{item.ticker}</span>
          <span
            className="sidebar-watchlist-change"
            style={{ color: (item.day_change_percent ?? 0) >= 0 ? "var(--color-success)" : "var(--color-danger)" }}
          >
            {item.day_change_percent != null ? `${item.day_change_percent >= 0 ? "+" : ""}${item.day_change_percent.toFixed(1)}%` : "—"}
          </span>
          <button className="sidebar-watchlist-remove" onClick={(e) => handleRemove(item.ticker, e)} aria-label={`Remove ${item.ticker}`}>
            ×
          </button>
        </div>
      ))}

      <div className="sidebar-watchlist-add" onClick={() => onNavigate("search")}>
        + Add ticker
      </div>
    </div>
  )
}

export default SidebarWatchlist