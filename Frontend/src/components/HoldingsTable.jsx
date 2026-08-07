import { useState } from "react"
import SentimentBadge from "./SentimentBadge"
import BullBearPanel from "./BullBearPanel"
import { IconAlertTriangle, IconBolt } from "@tabler/icons-react"

// NOTE: no longer fetches its own data - Dashboard.jsx fetches /holdings
// once and passes the result down as the `holdings` prop below. This
// component is now purely: given holdings, render the table + concentration
// alert + bull/bear panels. Loading/error/empty states are handled one
// level up, in Dashboard.jsx, before this component ever renders.
function HoldingsTable({ holdings }) {
  // Controls which gain/loss view is currently shown - toggled by the
  // buttons below. Both values are always present in the /holdings response,
  // so switching this doesn't require any new fetch - just re-reads a
  // different field from data we already have.
  const [view, setView] = useState("all-time") // "all-time" or "today"

  // Holdings flagged by the backend as over the concentration threshold
  const overweightHoldings = holdings.filter(h => h.overweight_flag)

  // Calculates all-time gain/loss on the frontend from avg_cost and
  // current_price. Note: the backend already sends this same info as
  // total_gain_loss / total_gain_loss_percent - this function duplicates
  // that math. Not broken, just worth eventually simplifying to just
  // read h.total_gain_loss directly instead.
  function calculateGainLoss(h) {
    const gainLoss = (h.current_price - h.avg_cost) * h.shares
    const gainLossPercent = ((h.current_price - h.avg_cost) / h.avg_cost) * 100
    return { gainLoss, gainLossPercent }
  }

  // holdings is guaranteed non-empty here - Dashboard.jsx already checked
  // loading/error/empty states before rendering this component at all.
  return (
    <div>
      <style>{`
        .holdings-table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
        .holdings-table th, .holdings-table td { padding: 0.5rem 1rem; text-align: left; border-bottom: 1px solid var(--color-border); }
        .holdings-table th { background: var(--color-surface); color: var(--color-text-secondary); font-weight: 500; }
        .holdings-table tbody tr:nth-child(even) { background: var(--color-surface-alt); }
        .concentration-alert { ... margin-bottom: var(--space-md); }
        .sentiment-positive { background: var(--color-success-bg); color: var(--color-success); }
        .sentiment-negative { background: var(--color-danger-bg); color: var(--color-danger); }
        .sentiment-neutral { background: var(--color-surface); color: var(--color-text-secondary); }
        .sentiment-loading { color: var(--color-text-muted); }
        .sentiment-unavailable { color: var(--color-text-muted); }
        .sentiment-badge { padding: 0.2rem 0.65rem; border-radius: 999px; font-size: var(--text-xs); text-transform: capitalize; display: inline-block; }
      `}</style>

      {/* Only shown at all if at least one holding is flagged overweight */}
      {overweightHoldings.length > 0 && (
        <div className="concentration-alert">
          <strong style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <IconAlertTriangle size={16} /> Concentration warning
          </strong>
          <ul>
            {overweightHoldings.map((h) => (
              <li key={h.ticker}>
                {h.ticker} makes up {h.percentage.toFixed(1)}% of your portfolio — consider whether this level of concentration matches your risk tolerance.
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Toggle buttons - just flip local "view" state, no new fetch needed */}
      <div style={{ marginBottom: "var(--space-sm)" }}>
        <button
          onClick={() => setView("all-time")}
          style={{ fontWeight: view === "all-time" ? "bold" : "normal" }}
        >
          All-time
        </button>
        <button
          onClick={() => setView("today")}
          style={{ fontWeight: view === "today" ? "bold" : "normal" }}
        >
          Today
        </button>
      </div>

      <table className="holdings-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Shares</th>
            <th>Avg Cost</th>
            <th>Current Price</th>
            <th>Gain/Loss</th>
            <th>Value</th>
            <th>% of Portfolio</th>
            <th>Sentiment</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            // Frontend-calculated all-time values (see note on calculateGainLoss above)
            const activeGainLoss = view === "all-time" ? h.total_gain_loss : h.day_gain_loss

            // Whichever value is currently relevant, based on the toggle -
            // used for both the displayed text AND the color below
            const activeGainLossPercent = view === "all-time" ? h.total_gain_loss_percent : h.day_gain_loss_percent

            return (
              <tr key={h.ticker} style={h.overweight_flag ? { color: "var(--color-danger)" } : {}}>
                <td>{h.ticker}</td>
                <td>{h.shares}</td>
                <td>${h.avg_cost.toFixed(2)}</td>
                <td>${h.current_price.toFixed(2)}</td>
                <td style={{ color: activeGainLoss >= 0 ? "var(--color-success)" : "var(--color-danger)" }}>
                  {`${activeGainLoss >= 0 ? "+" : ""}$${activeGainLoss.toFixed(2)} (${activeGainLossPercent.toFixed(1)}%)`}
                </td>
                <td>${h.value.toFixed(2)}</td>
                <td>{h.percentage.toFixed(1)}%</td>
                <td><SentimentBadge ticker={h.ticker} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* AI bull/bear analysis - one panel per holding */}
      <div style={{ marginTop: "var(--space-lg)" }}>
        <p style={{ fontWeight: "var(--font-weight-medium)", fontSize: "var(--text-md)" }}>AI analysis</p>
        {holdings.map((h) => (
          <div key={h.ticker} style={{ marginBottom: "0.5rem" }}>
            <span style={{ fontWeight: "var(--font-weight-medium)" }}>{h.ticker}</span>
            <BullBearPanel ticker={h.ticker} />
          </div>
        ))}
      </div>
    </div>
  )
}

export default HoldingsTable