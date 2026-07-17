import { useState, useEffect } from "react"

function HoldingsTable() {
  const [holdings, setHoldings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch("http://127.0.0.1:8000/holdings")
      .then(response => response.json())
      .then(data => {
        setHoldings(data.holdings)
        setLoading(false)
      })
      .catch(error => {
        setError(error.message)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return <p>Loading your holdings...</p>
  }

  if (error) {
    return <p style={{ color: "red" }}>Failed to load holdings: {error}</p>
  }

  if (holdings.length === 0) {
    return <p>No holdings yet — log a trade to get started.</p>
  }

  const overweightHoldings = holdings.filter(h => h.overweight_flag)

  return (
    <div>
      <style>{`
        .holdings-table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
        .holdings-table th, .holdings-table td { padding: 0.5rem 1rem; text-align: left; border-bottom: 1px solid #333; }
        .holdings-table th { background: #1a1a1a; }
        .holdings-table tbody tr:nth-child(even) { background: #111; }
        .concentration-alert {
  background: #3a1a1a;
  border: 1px solid #cc4444;
  color: #ffb3b3;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}
.concentration-alert ul {
  margin: 0.5rem 0 0 1.25rem;
}
      `}</style>
        {overweightHoldings.length > 0 && (
             <div className="concentration-alert">
                <strong>⚠️ Concentration Warning</strong>
                 <ul>
                    {overweightHoldings.map((h) => (
                        <li key={h.ticker}>
                            {h.ticker} makes up {h.percentage.toFixed(1)}% of your portfolio — consider whether this level of concentration matches your risk tolerance.
                        </li>
                     ))}
                 </ul>
             </div>
            )}
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