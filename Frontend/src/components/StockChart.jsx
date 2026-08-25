import { useState, useEffect } from "react"
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts"
import { apiFetch } from "../api"

const RANGES = ["1D", "1W", "1M", "3M", "1Y", "ALL"]

function StockChart({ ticker }) {
  const [range, setRange] = useState("1M")
  const [points, setPoints] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/stock/${ticker}/history?range=${range}`)
      .then((res) => res.json())
      .then((data) => setPoints(data.points || []))
      .catch(() => setPoints([]))
      .finally(() => setLoading(false))
  }, [ticker, range])

  return (
    <div>
      <div style={{ display: "flex", gap: "4px", marginBottom: "12px" }}>
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            style={{
              padding: "4px 10px",
              fontSize: "var(--text-xs)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--color-border)",
              background: range === r ? "var(--color-surface)" : "transparent",
              color: range === r ? "var(--color-text-primary)" : "var(--color-text-secondary)",
              cursor: "pointer",
            }}
          >
            {r}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>Loading chart…</p>
      ) : points.length === 0 ? (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>No chart data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={380}>
          <AreaChart data={points}>
            <defs>
              <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis domain={["auto", "auto"]} hide />
            <Tooltip
              contentStyle={{ background: "#1a1a1a", border: "1px solid #333", borderRadius: "6px" }}
              labelStyle={{ color: "#a0a0a0" }}
              formatter={(value) => [`$${value.toFixed(2)}`, "Close"]}
              labelFormatter={(label) => new Date(label).toLocaleString()}
            />
            <Area type="monotone" dataKey="close" stroke="#2dd4bf" strokeWidth={2} fill="url(#chartFill)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default StockChart