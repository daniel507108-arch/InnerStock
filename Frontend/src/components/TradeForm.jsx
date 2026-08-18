import { useState } from "react"
import { apiFetch } from "../api"

// All the state, validation, and submit logic below is UNCHANGED from the
// current version — same fields, same validate() rules, same handleSubmit
// flow, same handleTickerBlur auto-price-fill behavior. This pass only
// changes what gets returned at the bottom: a plain stacked <form> becomes
// the mockup's two-card layout ("The trade" mechanics + "Your reasoning"),
// and the raw <select>/<input type="number"> controls for action and
// conviction become tappable button rows.
function TradeForm({ onTradeLogged }) {
  const [form, setForm] = useState({
    ticker: "",
    action: "buy",
    quantity: "",
    price_per_share: "",
    trade_date: "",
    thesis_text: "",
    conviction_score: 3,
    review_date: "",
  })

  const [status, setStatus] = useState(null)
  const [errorMessage, setErrorMessage] = useState("")

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  // New — replaces the old <select name="action">. Same effect (writes
  // "buy" or "sell" into form.action), just triggered by clicking one of
  // the two toggle buttons instead of picking from a dropdown.
  function handleActionClick(action) {
    setForm((prev) => ({ ...prev, action }))
  }

  function handleConvictionClick(score) {
    setForm((prev) => ({ ...prev, conviction_score: score }))
  }

  function validate() {
    if (!form.ticker.trim()) return "Ticker is required."
    if (!form.quantity || Number(form.quantity) <= 0) return "Quantity must be greater than 0."
    if (!form.price_per_share || Number(form.price_per_share) <= 0) return "Price must be greater than 0."
    if (!form.trade_date) return "Trade date is required."
    if (!form.thesis_text.trim()) return "You must write a thesis before logging this trade."
    if (form.conviction_score < 1 || form.conviction_score > 5) return "Conviction score must be between 1 and 5."
    if (!form.review_date) return "Review date is required."
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()

    const validationError = validate()
    if (validationError) {
      setStatus("error")
      setErrorMessage(validationError)
      return
    }

    try {
      const response = await apiFetch("/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Something went wrong saving this trade.")
      }

      setStatus("success")
      setErrorMessage("")
      setForm({
        ticker: "", action: "buy", quantity: "", price_per_share: "",
        trade_date: "", thesis_text: "", conviction_score: 3, review_date: "",
      })
      onTradeLogged()
    } catch (err) {
      setStatus("error")
      setErrorMessage(err.message)
    }
  }

  async function handleTickerBlur() {
    if (!form.ticker || form.price_per_share !== "") return

    try {
      const response = await apiFetch(`/stock/${form.ticker}`)
      if (!response.ok) return

      const data = await response.json()
      if (data.price) {
        setForm((prev) => ({ ...prev, price_per_share: data.price }))
      }
    } catch (err) {
      // Convenience feature — fails silently, user can type the price manually.
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {/* .trade-grid (theme.css) is a 2-column grid: mechanics card on the
          left, reasoning card on the right, matching the mockup 1:1. Both
          cards sit inside the SAME <form>, so one submit button below
          covers both halves — splitting them visually doesn't require
          splitting them functionally. */}
      <div className="trade-grid">
        <div className="trade-card">
          <h3>The trade</h3>

          <div className="field">
            <label>Ticker</label>
            <input
              name="ticker"
              value={form.ticker}
              onChange={(e) => setForm((prev) => ({ ...prev, ticker: e.target.value.toUpperCase() }))}
              onBlur={handleTickerBlur}
              placeholder="e.g. AAPL"
            />
          </div>

          <div className="field">
            <label>Action</label>
            <div className="action-toggle">
              <button
                type="button"
                className={`buy${form.action === "buy" ? " active" : ""}`}
                onClick={() => handleActionClick("buy")}
              >
                Buy
              </button>
              <button
                type="button"
                className={`sell${form.action === "sell" ? " active" : ""}`}
                onClick={() => handleActionClick("sell")}
              >
                Sell
              </button>
            </div>
          </div>

          <div className="row-2">
            <div className="field">
              <label>Quantity</label>
              <input name="quantity" type="number" value={form.quantity} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Price / share</label>
              <input name="price_per_share" type="number" value={form.price_per_share} onChange={handleChange} />
            </div>
          </div>

          <div className="row-2">
            <div className="field">
              <label>Trade date</label>
              <input name="trade_date" type="date" value={form.trade_date} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Review date</label>
              <input name="review_date" type="date" value={form.review_date} onChange={handleChange} />
            </div>
          </div>
        </div>

        <div className="trade-card reasoning-card">
          <div className="reasoning-prompt">What's your reasoning?</div>

          <div className="field">
            <textarea name="thesis_text" value={form.thesis_text} onChange={handleChange} />
          </div>

          <div className="field">
            <label>Conviction</label>
            <div className="conviction-row">
              {[1, 2, 3, 4, 5].map((score) => (
                <button
                  key={score}
                  type="button"
                  className={`conviction-btn${form.conviction_score === score ? " active" : ""}`}
                  onClick={() => handleConvictionClick(score)}
                >
                  {score}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "var(--space-lg)" }}>
        <button type="submit" className="btn btn-primary">
          Save trade
        </button>
      </div>

      {status === "success" && <p style={{ color: "var(--color-success)" }}>Trade logged successfully.</p>}
      {status === "error" && <p style={{ color: "var(--color-danger)" }}>{errorMessage}</p>}
    </form>
  )
}

export default TradeForm
