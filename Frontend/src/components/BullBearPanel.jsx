import { useState } from "react"

function BullBearPanel({ ticker }) {
  const [expanded, setExpanded] = useState(false)
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
      const response = await fetch(`http://127.0.0.1:8000/bullbear/${ticker}`)
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
      <button onClick={handleToggle} disabled={loading}>
        {loading ? "Loading..." : expanded ? "Hide AI analysis" : "View AI analysis"}
      </button>

      {error && <p style={{ color: "red", fontSize: "0.85rem" }}>{error}</p>}

      {expanded && data && (
        <div style={{ border: "1px solid #333", borderRadius: "6px", padding: "0.75rem", marginTop: "0.5rem" }}>
          <p><strong>Bull case:</strong> {data.bull_case}</p>
          <p><strong>Bear case:</strong> {data.bear_case}</p>
          <p><strong>Key risks:</strong> {data.key_risks}</p>
        </div>
      )}
    </div>
  )
}

export default BullBearPanel