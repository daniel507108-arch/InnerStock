import { useState, useEffect } from "react"
import { apiFetch } from "../api"

// The backend sends ONE combined string with three labeled sections —
// "Bull Case: ... Bear Case: ... Key Risk: ..." — not three separate
// fields (this is a documented, low-priority contract mismatch: David's
// endpoint was supposed to split these, it doesn't). This function is
// the client-side workaround: split on each label using a lookahead so
// the labels themselves are kept as the start of their section, then
// bucket each section into { bull, bear, risk } by matching its label.
// If the backend ever does start returning 3 real fields, this whole
// function goes away and the component just reads data.bull_case /
// data.bear_case / data.key_risk directly.
function parseAnalysis(text) {
  const sections = text.split(/(?=Bull Case:|Bear Case:|Key Risk:)/)
  const result = { bull: "", bear: "", risk: "" }

  sections.forEach((section) => {
    const [label, ...rest] = section.split(":")
    const body = rest.join(":").trim()
    if (label.includes("Bull")) result.bull = body
    else if (label.includes("Bear")) result.bear = body
    else if (label.includes("Key Risk")) result.risk = body
  })

  return result
}

function BullBearPanel({ ticker, forceExpanded }) {
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

  // Auto-fetches once when this panel is forced open (i.e. rendered
  // inside HoldingsTable's expand-row) and nothing's loaded yet. Moved
  // below handleToggle's declaration purely for readability — a `function`
  // declaration like handleToggle is hoisted, so this would have worked
  // either way, but reading the effect after the function it calls is
  // easier to follow top-to-bottom than the original ordering.
  useEffect(() => {
    if (forceExpanded && !data) {
      handleToggle()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceExpanded])

  // Parsed once per successful fetch, not on every render — cheap regex
  // either way at this size, but there's no reason to re-split the same
  // string on every re-render when `data` hasn't changed.
  const sections = data ? parseAnalysis(data.analysis) : null

  const body = (
    <>
      {loading && <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)", margin: 0 }}>Loading analysis...</p>}
      {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)", margin: 0 }}>{error}</p>}

      {expanded && sections && (
        <>
          <div className="bullbear">
            <div className="bull">
              <h4>Bull case</h4>
              <p>{sections.bull}</p>
            </div>
            <div className="bear">
              <h4>Bear case</h4>
              <p>{sections.bear}</p>
            </div>
          </div>
          {sections.risk && (
            <div className="bullbear-risk">
              <h4>Key risk</h4>
              <p>{sections.risk}</p>
            </div>
          )}
        </>
      )}
    </>
  )

  // Two render paths on purpose:
  //  - forceExpanded (used inside HoldingsTable's expand-row): no toggle
  //    button, no extra bordered box — the table row already supplies the
  //    surrounding frame, so this just renders the bull/bear/risk content
  //    directly, matching the mockup's expanded-row layout exactly.
  //  - standalone (forceExpanded is false, if this is ever used elsewhere
  //    on its own): keeps its own toggle button and a bordered/background
  //    frame around the content, since there's no parent row supplying one.
  if (forceExpanded) {
    return <div>{body}</div>
  }

  return (
    <div style={{ marginTop: "0.4rem" }}>
      <button
        onClick={handleToggle}
        disabled={loading}
        className="btn"
        style={{ cursor: loading ? "default" : "pointer" }}
      >
        {loading ? "Loading..." : expanded ? "Hide AI analysis" : "View AI analysis"}
      </button>
      {(loading || error || expanded) && <div className="bullbear-frame">{body}</div>}
    </div>
  )
}

export default BullBearPanel
