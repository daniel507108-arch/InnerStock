import { useState, useEffect } from "react"
import StatsCards from "./StatsCards"
import HoldingsTable from "./HoldingsTable"
import { apiFetch } from "../api"

// Owns the ONE /holdings fetch for the whole dashboard view. StatsCards and
// HoldingsTable both need this same data - fetching it once here and passing
// it down as props avoids two components independently hitting the same
// endpoint on every page load.
function Dashboard({ refreshKey }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    apiFetch("/holdings")
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load holdings")
        return response.json()
      })
      .then((result) => {
        setData(result)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [refreshKey]) // re-fetch whenever a trade is logged, same pattern as before

  // Three states, checked top to bottom, same pattern HoldingsTable used to
  // have - just centralized here now so children don't each need their own.
  if (loading) return <p style={{ color: "var(--color-text-secondary)" }}>Loading your dashboard...</p>
  if (error) return <p style={{ color: "var(--color-danger)" }}>Failed to load dashboard: {error}</p>
  if (!data || data.holdings.length === 0) return <p>No holdings yet — log a trade to get started.</p>

  // Only reached once data has actually arrived - safe to pass straight
  // through to both children below.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-lg)" }}>
      <StatsCards
        totalValue={data.total_value}
        dayChangePercent={data.day_change_percent}
        positionCount={data.position_count}
        avgConviction={data.avg_conviction}
      />
      <HoldingsTable holdings={data.holdings} />
    </div>
  )
}

export default Dashboard