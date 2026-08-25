import { useState } from "react"
import { IconSearch } from "@tabler/icons-react"
import { searchTickers } from "../tickers"
import { apiFetch } from "../api"
import StockChart from "./StockChart"

function SearchPage() {
  const [query, setQuery] = useState("")
  const [matches, setMatches] = useState([])
  const [selected, setSelected] = useState(null)
  const [info, setInfo] = useState(null)
  const [error, setError] = useState(null)
  const [watchlistStatus, setWatchlistStatus] = useState(null) // null | "adding" | "added" | "error"

  function handleQueryChange(value) {
    setQuery(value)
    setMatches(searchTickers(value))
  }

  async function selectTicker(ticker) {
    setSelected(ticker)
    setQuery(ticker)
    setMatches([])
    setInfo(null)
    setError(null)
    setWatchlistStatus(null)

    try {
      const res = await apiFetch(`/stock/${ticker}`)
      if (!res.ok) {
        setError(`Couldn't find data for "${ticker}".`)
        return
      }
      setInfo(await res.json())
    } catch {
      setError(`Couldn't find data for "${ticker}".`)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim()) return
    // Exact-symbol fallback if nothing in the static list matched
    await selectTicker(query.trim().toUpperCase())
  }

  async function handleAddToWatchlist() {
    if (!selected) return
    setWatchlistStatus("adding")
    try {
      const res = await apiFetch("/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: selected }),
      })
      if (res.ok || res.status === 409) {
        setWatchlistStatus("added")

              if (res.ok || res.status === 409) {
        setWatchlistStatus("added")
        window.dispatchEvent(new Event("watchlist-updated"))
      } else 
        setWatchlistStatus("error")
      }
    } catch {
      setWatchlistStatus("error")
    }
  }

  return (
    <div style={{ padding: "20px" }}>
      <h2 style={{ fontWeight: 500, fontSize: "20px", marginBottom: "16px" }}>Search</h2>

      <form onSubmit={handleSubmit} style={{ position: "relative", marginBottom: "24px", maxWidth: "480px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", padding: "8px 12px" }}>
          <IconSearch size={16} color="var(--color-text-secondary)" />
          <input
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search ticker or company name"
            style={{ background: "transparent", border: "none", outline: "none", color: "var(--color-text-primary)", fontSize: "var(--text-base)", flex: 1 }}
          />
        </div>

        {matches.length > 0 && (
          <div style={{ position: "absolute", top: "100%", left: 0, right: 0, background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", marginTop: "4px", zIndex: 10 }}>
            {matches.map((m) => (
              <div
                key={m.ticker}
                onClick={() => selectTicker(m.ticker)}
                style={{ padding: "8px 12px", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
              >
                <span>{m.ticker}</span>
                <span style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>{m.name}</span>
              </div>
            ))}
          </div>
        )}
      </form>

      {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

      {info && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <div style={{ fontSize: "18px", fontWeight: 500 }}>{info.ticker}</div>
              <div style={{ fontSize: "24px", fontWeight: 500 }}>${info.price?.toFixed(2)}</div>
            </div>
            <button
              onClick={handleAddToWatchlist}
              disabled={watchlistStatus === "adding" || watchlistStatus === "added"}
              style={{
                background: watchlistStatus === "added" ? "var(--color-surface)" : "var(--color-accent)",
                color: watchlistStatus === "added" ? "var(--color-text-secondary)" : "var(--color-accent-ink)",
                border: "none",
                borderRadius: "var(--radius-sm)",
                padding: "8px 16px",
                fontSize: "var(--text-sm)",
                fontWeight: 500,
                cursor: watchlistStatus === "added" ? "default" : "pointer",
              }}
            >
              {watchlistStatus === "added" ? "On your watchlist" : watchlistStatus === "adding" ? "Adding…" : "+ Add to watchlist"}
            </button>
          </div>

          <StockChart ticker={info.ticker} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "16px", marginTop: "24px" }}>
            <div>
              <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>Market cap</div>
              <div>{info.market_cap ? `$${(info.market_cap / 1e9).toFixed(2)}B` : "—"}</div>
            </div>
            <div>
              <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>P/E ratio</div>
              <div>{info.pe_ratio ? info.pe_ratio.toFixed(2) : "—"}</div>
            </div>
            <div>
              <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}>Sector</div>
              <div>{info.sector || "—"}</div>
            </div>
          </div>
        </div>
      )}

      {!info && !error && (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>
          Search for a ticker to see its price chart and fundamentals.
        </p>
      )}
    </div>
  )
}

export default SearchPage