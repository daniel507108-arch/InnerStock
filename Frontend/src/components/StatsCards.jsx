// Single reusable card - renders one label/value pair. Used 4 times below
// so the card's own styling only has to be defined once.
function StatCard({ label, value, valueColor }) {
  return (
    <div
      style={{
        background: "var(--color-surface)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-md)",
        flex: "1 1 0",
      }}
    >
      <p style={{ margin: 0, color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>
        {label}
      </p>
      <p
        style={{
          margin: "4px 0 0",
          fontSize: "22px",
          fontWeight: "var(--font-weight-medium)",
          color: valueColor || "var(--color-text-primary)",
        }}
      >
        {value}
      </p>
    </div>
  )
}

// Purely presentational - takes the 4 numbers straight from /holdings
// (already fetched once by Dashboard.jsx) and lays them out as cards.
// No fetching, no state - if the data's wrong, the bug is in Dashboard.jsx
// or the backend, not here.
function StatsCards({ totalValue, dayChangePercent, positionCount, avgConviction }) {
  // Green for a gain/flat day, red for a loss - same convention as the
  // gain/loss coloring already used in HoldingsTable.
  const dayChangeColor = dayChangePercent >= 0 ? "var(--color-success)" : "var(--color-danger)"
  const dayChangeSign = dayChangePercent >= 0 ? "+" : ""

  return (
    <div style={{ display: "flex", gap: "var(--space-md)", flexWrap: "wrap" }}>
      <StatCard
        label="Total value"
        value={`$${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
      />
      <StatCard
        label="Today"
        value={`${dayChangeSign}${dayChangePercent.toFixed(1)}%`}
        valueColor={dayChangeColor}
      />
      <StatCard label="Positions" value={positionCount} />
      <StatCard label="Avg conviction" value={`${avgConviction.toFixed(1)}/5`} />
    </div>
  )
}

export default StatsCards