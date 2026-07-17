import { useState, useEffect } from "react"

function HoldingsTable() {
  // Starts as an empty array — there's nothing to show before the fetch finishes.
  const [holdings, setHoldings] = useState([])

  // Tracks whether we're still waiting on the backend. Starts true, since
  // the very first thing that happens is: we haven't gotten data back yet.
  const [loading, setLoading] = useState(true)

  // Holds an error message if the fetch fails, or null if everything's fine.
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch("http://127.0.0.1:8000/holdings")
      .then(response => response.json())
      .then(data => {
        setHoldings(data.holdings)
        setLoading(false) // data arrived, no longer loading
      })
      .catch(error => {
        setError(error.message)
        setLoading(false) // failed, but also no longer "loading"
      })
  }, []) // empty [] means "run this once, right when the component first appears"

  // Three possible states, checked in order, top to bottom:

  if (loading) {
    return <p>Loading your holdings...</p>
  }

  if (error) {
    return <p style={{ color: "red" }}>Failed to load holdings: {error}</p>
  }

  if (holdings.length === 0) {
    return <p>No holdings yet — log a trade to get started.</p>
  }

  // Only reached once loading is done, there's no error, AND holdings has data.
  return (
  <div>
    <style>{`
      .holdings-table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
      .holdings-table th, .holdings-table td { padding: 0.5rem 1rem; text-align: left; border-bottom: 1px solid #333; }
      .holdings-table th { background: #1a1a1a; }
      .holdings-table tbody tr:nth-child(even) { background: #111; }
    `}</style>

    <table className="holdings-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Shares</th>
          <th>Current Price</th>
          <th>Value</th>
          <th>% of Portfolio</th>
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => (
          <tr key={h.ticker} style={h.overweight_flag ? { color: "red" } : {}}>
            <td>{h.ticker}</td>
            <td>{h.shares}</td>
            <td>${h.current_price.toFixed(2)}</td>
            <td>${h.value.toFixed(2)}</td>
            <td>{h.percentage.toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)
}

export default HoldingsTable