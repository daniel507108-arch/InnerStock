import { useState } from "react"
import { apiFetch } from "../api"

// All the state, validation, and submit logic below is UNCHANGED from the
// current version — same fields, same validate() rules, same handleSubmit
// flow. This pass only changes what gets returned at the bottom: a plain
// stacked <form> becomes the mockup's two-card layout ("The trade"
// mechanics + "Your reasoning"), and the raw <select>/<input type="number">
// controls for action and conviction become tappable button rows.
function TradeForm({ onTradeLogged }) {
  const [form, setForm] = useState({
    ticker: "",
    action: "buy",
    quantity: "",
    price_per_share: "",
    trade_date: "",
    trade_time: "", // NEW - optional, powers the intraday price auto-fill
    thesis_text: "",
    conviction_score: 3,
    review_date: "",
  })

  const [status, setStatus] = useState(null)
  const [errorMessage, setErrorMessage] = useState("")
  // NEW - set when the auto-filled price came from a daily-close fallback
  // rather than an exact intraday match, so the user isn't misled into
  // thinking it's more precise than it actually is.
  const [priceNote, setPriceNote] = useState("")
  // NEW - true only when the current price_per_share value came from our
  // own auto-fill, not something the user typed. handlePriceAutofill needs
  // this to tell "field is empty" apart from "field already has a value I
  // set myself and can safely replace with a better one" - e.g. filling in
  // a daily-close price on ticker+date blur, then refining it to an exact
  // intraday match once trade_time is filled in too. A manually-typed
  // price is never touched either way.
  const [priceAutofilled, setPriceAutofilled] = useState(false)

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    // Manual edit overrides whatever the auto-fill suggested, so the
    // precision note no longer applies and this is no longer a value
    // we're free to silently replace.
    if (name === "price_per_share") {
      setPriceNote("")
      setPriceAutofilled(false)
    }
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
      // trade_time is optional - send null instead of "" when left blank,
      // since the backend's Optional[time] field rejects an empty string.
      const payload = { ...form, trade_time: form.trade_time || null }
      const response = await apiFetch("/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Something went wrong saving this trade.")
      }

      setStatus("success")
      setErrorMessage("")
      setForm({
        ticker: "", action: "buy", quantity: "", price_per_share: "",
        trade_date: "", trade_time: "", thesis_text: "", conviction_score: 3, review_date: "",
      })
      setPriceNote("")
      setPriceAutofilled(false)
      onTradeLogged()
    } catch (err) {
      setStatus("error")
      setErrorMessage(err.message)
    }
  }

  // Auto-fills price_per_share as accurately as we can manage. Runs on
  // blur of ticker, trade_date, AND trade_time - whichever field the user
  // finishes last is what actually has enough info to fetch a price, so
  // all three trigger the same check rather than just the ticker field.
  //
  // Without a trade_date yet, there's nothing to look up a historical
  // price for, so this falls back to the old behavior: just grab whatever
  // the current live price is, same as before this feature existed. Once
  // a date is known, we ask /stock/{ticker}/price-at instead, which is
  // aware of trade_time (for a precise intraday match, when available)
  // and falls back to that day's close otherwise - see the backend
  // endpoint's docstring for why intraday only works within ~7 days.
  async function handlePriceAutofill() {
    // Skip only when there's a price we DIDN'T set ourselves - i.e. the
    // user typed it in by hand. A price we auto-filled earlier (from an
    // ticker/date-only lookup, before trade_time was known) is fair game
    // to replace with something more precise.
    if (!form.ticker || (form.price_per_share !== "" && !priceAutofilled)) return

    if (!form.trade_date) {
      try {
        const response = await apiFetch(`/stock/${form.ticker}`)
        if (!response.ok) return
        const data = await response.json()
        if (data.price) {
          setForm((prev) => ({ ...prev, price_per_share: data.price }))
          setPriceNote("")
          setPriceAutofilled(true)
        }
      } catch {
        // Convenience feature — fails silently, user can type the price manually.
      }
      return
    }

    try {
      const params = new URLSearchParams({ trade_date: form.trade_date })
      if (form.trade_time) params.set("trade_time", form.trade_time)

      const response = await apiFetch(`/stock/${form.ticker}/price-at?${params}`)
      if (!response.ok) return

      const data = await response.json()
      if (data.price) {
        setForm((prev) => ({ ...prev, price_per_share: data.price }))
        setPriceNote(data.precision === "daily-close" ? data.note : "")
        setPriceAutofilled(true)
      }
    } catch {
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
              onBlur={handlePriceAutofill}
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
              {/* NEW - only shown when the auto-filled price came from a
                  daily close rather than an exact intraday match, so the
                  user knows it's a less precise number. Clears itself as
                  soon as the price field is edited by hand. */}
              {priceNote && (
                <p style={{ margin: "4px 0 0", fontSize: "var(--text-xs)", color: "var(--color-text-secondary)" }}>
                  {priceNote}
                </p>
              )}
            </div>
          </div>

          <div className="row-2">
            <div className="field">
              <label>Trade date</label>
              <input
                name="trade_date"
                type="date"
                value={form.trade_date}
                onChange={handleChange}
                onBlur={handlePriceAutofill}
              />
            </div>
            <div className="field">
              {/* NEW - optional. Powers an exact intraday price match
                  instead of the daily-close fallback, but only within
                  yfinance's ~7-day intraday history window - see
                  handlePriceAutofill's comment for why. */}
              <label>Trade time (optional)</label>
              <input
                name="trade_time"
                type="time"
                value={form.trade_time}
                onChange={handleChange}
                onBlur={handlePriceAutofill}
              />
            </div>
          </div>

          <div className="field">
            <label>Review date</label>
            <input name="review_date" type="date" value={form.review_date} onChange={handleChange} />
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
