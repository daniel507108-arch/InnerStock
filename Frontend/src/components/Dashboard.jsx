import { useState, useEffect } from "react"
import StatsCards from "./StatsCards"
import HoldingsTable from "./HoldingsTable"
import { apiFetch } from "../api"

// Owns the ONE /holdings fetch for the whole dashboard view, same as
// before — no data-fetching logic changes in this pass, only the JSX
// returned at the bottom. `onNavigate` is new: it lets the "+ Log a
// trade" button in the topbar jump straight to the trade-log tab. Pass
// `activeView`'s setter down from App.jsx (see roadmap step 5).
function Dashboard({ refreshKey, onNavigate }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [accuracyPercent, setAccuracyPercent] = useState(null)
  const [gradedCount, setGradedCount] = useState(null)

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
  }, [refreshKey])

  useEffect(() => {
  apiFetch("/trading-patterns")
    .then((response) => {
      if (!response.ok) throw new Error("not available")
      return response.json()
    })
    .then((result) => {
      // No flat accuracy_percent field — this endpoint returns a
      // by-conviction breakdown instead. Overall accuracy = sum of
      // "correct" across every bucket, divided by reviewed_count.
      if (result.reviewed_count > 0) {
        const totalCorrect = result.by_conviction.reduce((sum, b) => sum + b.correct, 0)
        setAccuracyPercent((totalCorrect / result.reviewed_count) * 100)
        setGradedCount(result.reviewed_count)
      } else {
        setAccuracyPercent(null)
        setGradedCount(null)
      }
    })
    .catch(() => {
      setAccuracyPercent(null)
      setGradedCount(null)
    })
}, [refreshKey])
  // Topbar is identical across all three loading/error/empty/loaded states,
  // so it's pulled out once here instead of repeated in every early return
  // below — that's the main structural change from the old version, which
  // returned a bare <p> with no shell at all while loading.
  const topbar = (
    <div className="topbar">
      <div>
        <h1>Dashboard</h1>
        <div className="sub">Portfolio &amp; behavioral overview</div>
      </div>
      <button className="btn btn-accent" onClick={() => onNavigate?.("logtrade")}>
        + Log a trade
      </button>
    </div>
  )

  if (loading) {
    return (
      <>
        {topbar}
        <div className="content">
          <p style={{ color: "var(--color-text-secondary)" }}>Loading your dashboard...</p>
        </div>
      </>
    )
  }

  if (error) {
    return (
      <>
        {topbar}
        <div className="content">
          <p style={{ color: "var(--color-danger)" }}>Failed to load dashboard: {error}</p>
        </div>
      </>
    )
  }

  if (!data || data.holdings.length === 0) {
    return (
      <>
        {topbar}
        <div className="content">
          <p style={{ color: "var(--color-text-secondary)" }}>
            No holdings yet — log a trade to get started.
          </p>
        </div>
      </>
    )
  }

  const dayChangeValue = data.holdings.reduce((sum, h) => sum + h.day_gain_loss, 0)
  const overweightCount = data.holdings.filter((h) => h.overweight_flag).length

  return (
    <>
      {topbar}
      <div className="content">
        
        <StatsCards
        totalValue={data.total_value}
        dayChangePercent={data.day_change_percent}
        dayChangeValue={dayChangeValue}
        positionCount={data.position_count}
        overweightCount={overweightCount}
        avgConviction={data.avg_conviction}
        accuracyPercent={accuracyPercent}
        gradedCount={gradedCount}
      />
        <HoldingsTable holdings={data.holdings} />
      </div>
    </>
  )
}

export default Dashboard
