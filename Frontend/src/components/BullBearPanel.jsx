import { useState, useEffect } from "react"
import { apiFetch } from "../api"

function BullBearPanel({ ticker, forceExpanded }) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (forceExpanded && !data) {
      handleToggle()
    }
  }, [forceExpanded])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleToggle() {
    // Already have the data — just show/hide it, no need to fetch again.
    if (data) {
      setExpanded(!expanded)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch(`/bullbear/${ticker}`)
      if (!response.ok) throw new Error("Analysis not available yet")
      const result = await response.json()
      setData(result)
      setExpanded(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginTop: "0.4rem" }}>
      {!forceExpanded && (
  <button onClick={handleToggle} disabled={loading} style={{
    background: "transparent",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-border-strong)",
    borderRadius: "var(--radius-sm)",
    padding: "0.4rem 0.8rem",
    cursor: loading ? "default" : "pointer",
  }}>
    {loading ? "Loading..." : expanded ? "Hide AI analysis" : "View AI analysis"}
  </button>
)}

{loading && forceExpanded && <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>Loading analysis...</p>}
{error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

     {expanded && data && (
  <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", padding: "0.85rem", marginTop: "0.5rem", background: "var(--color-surface-alt)" }}>
    {data.analysis.split(/(?=Bull Case:|Bear Case:|Key Risk:)/).map((section, i) => {
      const [label, ...rest] = section.split(":")
      return (
        <p key={i} style={{ marginBottom: "0.6rem", color: "var(--color-text-primary)" }}>
          <strong>{label}:</strong>{rest.join(":").trim()}
        </p>
      )
    })}
  </div>
)}
    </div>
  )
}

export default BullBearPanel


