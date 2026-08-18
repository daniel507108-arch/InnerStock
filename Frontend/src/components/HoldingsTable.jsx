import { useState, Fragment } from "react"
import SentimentBadge from "./SentimentBadge"
import BullBearPanel from "./BullBearPanel"
import { IconAlertTriangle } from "@tabler/icons-react"

// Still purely presentational — holdings comes from Dashboard.jsx's single
// /holdings fetch, this component only renders it. The `<style>` block that
// used to live here has moved to theme.css as .holdings-table / .pill-* /
// .concentration-banner etc., since those rules are shared shell classes
// now, not something unique to this one component.
function HoldingsTable({ holdings }) {
  const [view, setView] = useState("all-time") // "all-time" or "today"
  const [expandedTicker, setExpandedTicker] = useState(null)

  const overweightHoldings = holdings.filter((h) => h.overweight_flag)
  // Used to size the allocation bar relative to the biggest position in the
  // table, so the largest holding's bar reads as "full" and everything else
  // is proportional to it — a flat 0-100% scale would make every bar look
  // nearly empty once one position dominates the portfolio.
  const maxAllocation = Math.max(...holdings.map((h) => h.percentage), 1)

  
  return (
    <div className="card">
      <div className="card-head">
        <h2>Holdings</h2>
        {/* Same local-state toggle as before — both today/all-time fields
            are already present in every holding from the one /holdings
            fetch, so flipping this never triggers a new request. */}
        <div className="toggle-group">
          <button
            className={view === "today" ? "active" : ""}
            onClick={() => setView("today")}
          >
            Today
          </button>
          <button
            className={view === "all-time" ? "active" : ""}
            onClick={() => setView("all-time")}
          >
            All-time
          </button>
        </div>
      </div>

      <div style={{ padding: overweightHoldings.length > 0 ? "var(--space-md) var(--space-md) 0" : 0 }}>
        {overweightHoldings.length > 0 && (
          <div className="concentration-banner">
            <span>
              <IconAlertTriangle size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
              {overweightHoldings.length === 1 ? (
                <>
                  <strong>{overweightHoldings[0].ticker}</strong> is{" "}
                  {overweightHoldings[0].percentage.toFixed(0)}% of your portfolio — consider whether
                  this concentration matches your risk tolerance.
                </>
              ) : (
                <>
                  {overweightHoldings.map((h) => h.ticker).join(", ")} are flagged as overweight —
                  review your concentration.
                </>
              )}
            </span>
          </div>
        )}
      </div>

      <table className="holdings-table">
        <colgroup>
  <col style={{ width: "20%" }} />{/* Ticker */}
  <col style={{ width: "12%" }} />{/* Sentiment */}
  <col style={{ width: "10%" }} />{/* Shares */}
  <col style={{ width: "12%" }} />{/* Price */}
  <col style={{ width: "14%" }} />{/* Value */}
  <col style={{ width: "16%" }} />{/* Gain/Loss */}
  <col style={{ width: "12%" }} />{/* Allocation */}
  <col style={{ width: "4%" }} />{/* expand button */}
</colgroup>
        <thead>
          <tr>
            <th>Ticker</th>
            <th className="col-left">Sentiment</th>
            <th>Shares</th>
            <th>Price</th>
            <th>Value</th>
            <th>Gain/Loss</th>
            <th>Allocation</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const activeGainLoss = view === "all-time" ? h.total_gain_loss : h.day_gain_loss
            const activeGainLossPercent =
              view === "all-time" ? h.total_gain_loss_percent : h.day_gain_loss_percent
            const isExpanded = expandedTicker === h.ticker

            return (
              // This is the fix for the known Fragment-key bug: the shorthand
              // <>...</> CANNOT take a `key` prop, so wrapping each row pair
              // in it silently broke React's reconciliation across re-renders
              // (expand/collapse state, sentiment fetches, etc. could bleed
              // between tickers). `<Fragment key={h.ticker}>` is the same
              // "no extra DOM node" behavior but WITH a key.
              <Fragment key={h.ticker}>
                <tr>
                  <td>
                    <div className="ticker-cell">
                      <div className="ticker-badge">{h.ticker.slice(0, 2)}</div>
                      <div>
                        <div className="ticker-name">{h.ticker}</div>
                        <div className="ticker-shares">{h.shares.toFixed(4)} sh</div>
                      </div>
                    </div>
                  </td>
                  <td className="col-left">
                    <SentimentBadge ticker={h.ticker} />
                  </td>
                  <td>{h.shares.toFixed(4)}</td>
                  <td>${h.current_price.toFixed(2)}</td>
                  <td>${h.value.toFixed(2)}</td>
                  <td className={activeGainLoss >= 0 ? "gain-up" : "gain-down"}>
                    {activeGainLoss >= 0 ? "+" : ""}
                    ${activeGainLoss.toFixed(2)} ({activeGainLossPercent.toFixed(2)}%)
                  </td>
                  <td className={h.overweight_flag ? "overweight" : ""}>
                    {h.percentage.toFixed(0)}%
                    <div className="alloc-bar">
                      <div
                        className="alloc-fill"
                        style={{
                          width: `${(h.percentage / maxAllocation) * 100}%`,
                          background: h.overweight_flag ? "var(--color-warning)" : "var(--color-accent)",
                        }}
                      />
                    </div>
                  </td>
                  <td>
                    <button
                      className="expand-btn"
                      onClick={() => setExpandedTicker(isExpanded ? null : h.ticker)}
                    >
                      {isExpanded ? "▴" : "▾"}
                    </button>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="expand-row">
                    <td colSpan={8}>
                      <BullBearPanel ticker={h.ticker} forceExpanded />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default HoldingsTable
