import { useState, useEffect, useRef } from "react"
import StatsCards from "./StatsCards"
import HoldingsTable from "./HoldingsTable"
import { apiFetch } from "../api"

// How often the dashboard re-polls /holdings for updated prices while the
// tab is open. Paired with the backend's PRICE_CACHE_TTL_SECONDS (main.py) -
// kept slightly longer than that TTL so a poll actually lands on a fresh
// yfinance fetch instead of just re-reading the same cache row. This closes
// the "reload the page to see the real price" gap; it does not make prices
// literally tick-by-tick (yfinance's free data itself runs a bit behind the
// live market) - see the price-lag writeup for the tradeoffs.
const PRICE_POLL_INTERVAL_MS = 60_000

// Owns the ONE /holdings fetch for the whole dashboard view. `onNavigate` is
// new: it lets the "+ Log a trade" button in the topbar jump straight to the
// trade-log tab. Pass `activeView`'s setter down from App.jsx (see roadmap
// step 5). Also new: the /holdings fetch now repeats on an interval instead
// of firing once per mount, so prices stay current without the user having
// to manually reload.
function Dashboard({ refreshKey, onNavigate }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [accuracyPercent, setAccuracyPercent] = useState(null)
  const [gradedCount, setGradedCount] = useState(null)

  // Mirrors `data` so the poll's error handler can check "do we already have
  // something on screen" without depending on `data` directly - depending on
  // it would mean this whole effect (and its interval) tears down and
  // re-fires on every successful load, which defeats the point of an
  // interval. The ref always reflects the latest value; state is still what
  // actually drives rendering.
  const hasDataRef = useRef(false)

  useEffect(() => {
    let cancelled = false

    // isPoll: the very first call (mount, or refreshKey changing because a
    // trade was just logged) still shows the "Loading..." state as before.
    // Interval-driven refreshes fetch quietly in the background instead -
    // flipping loading back to true every 60s would blank out the whole
    // dashboard the user is actively looking at just to redraw the same
    // holdings with a new price.
    function loadHoldings(isPoll) {
      if (!isPoll) setLoading(true)
      apiFetch("/holdings")
        .then((response) => {
          if (!response.ok) throw new Error("Failed to load holdings")
          return response.json()
        })
        .then((result) => {
          if (cancelled) return
          setData(result)
          hasDataRef.current = true
          setLoading(false)
        })
        .catch((err) => {
          if (cancelled) return
          // A background poll failing (e.g. one flaky request) shouldn't
          // blow away an already-loaded dashboard with an error screen -
          // only surface the error if we don't have any data to show yet.
          if (!isPoll || !hasDataRef.current) setError(err.message)
          setLoading(false)
        })
    }

    loadHoldings(false)
    const intervalId = setInterval(() => loadHoldings(true), PRICE_POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(intervalId)
    }
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
