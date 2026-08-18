function StatCard({ label, value, valueColor, sub, subColor }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </div>
      {sub && <div className="stat-sub" style={subColor ? { color: subColor } : undefined}>{sub}</div>}
    </div>
  )
}

function StatsCards({
  totalValue,
  dayChangePercent,
  dayChangeValue,
  positionCount,
  overweightCount,
  avgConviction,
  accuracyPercent,
  gradedCount,
}) {
  const dayChangeColor = dayChangePercent >= 0 ? "var(--color-success)" : "var(--color-danger)"
  const dayChangeSign = dayChangePercent >= 0 ? "+" : ""

  return (
    <div className="stat-grid">
      <StatCard
        label="Total value"
        value={`$${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
        sub={`${positionCount} position${positionCount === 1 ? "" : "s"}`}
      />
      <StatCard
        label="Today"
        value={`${dayChangeSign}${dayChangePercent.toFixed(1)}%`}
        valueColor={dayChangeColor}
        sub={dayChangeValue !== undefined ? `${dayChangeSign}$${Math.abs(dayChangeValue).toFixed(0)}` : undefined}
        subColor={dayChangeColor}
      />
      <StatCard
        label="Positions"
        value={positionCount}
        sub={overweightCount > 0 ? `${overweightCount} overweight` : undefined}
      />
      <StatCard label="Avg. conviction" value={avgConviction.toFixed(1)} sub="out of 5" />

      {accuracyPercent !== null && accuracyPercent !== undefined && (
  <StatCard
    label="Thesis accuracy"
    value={`${accuracyPercent.toFixed(0)}%`}
    sub={gradedCount ? `${gradedCount} graded trade${gradedCount === 1 ? "" : "s"}` : undefined}
  />
)}
    </div>
  )
}

export default StatsCards