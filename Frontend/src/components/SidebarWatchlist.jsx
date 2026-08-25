import { useState, useEffect } from "react"
import { apiFetch } from "../api"

function SidebarWatchlist({ onNavigate }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  function fetchWatchlist() {
    apiFetch("/watchlist")
      .then((response) => (response.ok ? response.json() : { watchlist: [] }))
      .then((result) => setItems(result.watchlist || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchWatchlist()
    window.addEventListener("watchlist-updated", fetchWatchlist)
    return () => window.removeEventListener("watchlist-updated", fetchWatchlist)
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