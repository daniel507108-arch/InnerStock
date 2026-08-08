import { useState } from "react"

function TradeForm({ onTradeLogged }) {
  // One object holding every field in the form, instead of a separate
  // useState for each — easier to manage as the form grows.
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

  // Tracks whether the last submit attempt succeeded, failed, or hasn't happened yet.
  // null = no attempt yet, "success" = it worked, "error" = something went wrong.
  const [status, setStatus] = useState(null)
  const [errorMessage, setErrorMessage] = useState("")

  // Runs on every keystroke, for every input — reused across all fields.
  // e.target.name tells us WHICH field changed, e.target.value is its new value.
  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    // ...prev copies every other field as-is; [name]: value overwrites just this one
  }

  // Checks the form's contents BEFORE sending anything to the backend.
  // Returns null if everything looks fine, or a string describing the first problem found.
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

  // Runs when the form is submitted (button click OR pressing Enter in a field).
  async function handleSubmit(e) {
    e.preventDefault() // <-- this is the line that stops the page-reset behavior

    const validationError = validate()
    if (validationError) {
      // Stop here if validation fails — never even attempt the network request.
      setStatus("error")
      setErrorMessage(validationError)
      return
    }

    try {
      // Send the form data to the backend as JSON.
      const response = await fetch("http://127.0.0.1:8000/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })

      if (!response.ok) {
        // The backend responded, but with an error (e.g. bad data, server issue).
        const errorData = await response.json()
        throw new Error(errorData.detail || "Something went wrong saving this trade.")
      }

      // Success — clear the form so it's ready for the next trade.
      setStatus("success")
      setErrorMessage("")
      setForm({
        ticker: "", action: "buy", quantity: "", price_per_share: "",
        trade_date: "", thesis_text: "", conviction_score: 3, review_date: "",
      })
      onTradeLogged() // tell App.jsx a trade was just logged
    } catch (err) {
      // Covers both backend errors above AND total failures (backend not running, network issue).
      setStatus("error")
      setErrorMessage(err.message)
    }
  }
 const labelStyle = { display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }

async function handleTickerBlur() {
  // Don't bother if there's no ticker typed, or if the user already
  // manually entered a price — never overwrite something they typed themselves.
  if (!form.ticker || form.price_per_share !== "") return

  try {
    const response = await fetch(`http://127.0.0.1:8000/stock/${form.ticker}`)
    if (!response.ok) return // invalid ticker, or a graceful error — just leave price blank, no big deal

    const data = await response.json()
    if (data.price) {
      setForm((prev) => ({ ...prev, price_per_share: data.price }))
    }
  } catch (err) {
    // A convenience feature failing shouldn't interrupt the user —
    // fail silently, they can just type the price manually.
  }
}

function handleConvictionClick(score) {
  setForm((prev) => ({ ...prev, conviction_score: score }))
}

 return (
  <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)", maxWidth: "420px" }}>

    <div style={{ background: "var(--color-surface)", padding: "var(--space-md)", borderRadius: "var(--radius-md)" }}>
      <p style={{ margin: "0 0 var(--space-sm)", fontSize: "var(--text-sm)", fontWeight: "var(--font-weight-medium)", color: "var(--color-text-secondary)" }}>
        The trade
      </p>

      <div style={{ display: "flex", gap: "var(--space-sm)", marginBottom: "var(--space-sm)" }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          Ticker
          <input name="ticker" value={form.ticker} onChange={(e) => setForm((prev) => ({ ...prev, ticker: e.target.value.toUpperCase() }))} onBlur={handleTickerBlur} placeholder="e.g. AAPL" />
        </label>
        <label style={{ ...labelStyle, flex: 1 }}>
          Action
          <select name="action" value={form.action} onChange={handleChange}>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </label>
      </div>

      <div style={{ display: "flex", gap: "var(--space-sm)", marginBottom: "var(--space-sm)" }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          Quantity
          <input name="quantity" type="number" value={form.quantity} onChange={handleChange} />
        </label>
        <label style={{ ...labelStyle, flex: 1 }}>
          Price per share
          <input name="price_per_share" type="number" value={form.price_per_share} onChange={handleChange} />
          <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
            Auto-filled from today's price — edit if your fill price was different
          </span>
        </label>
      </div>

      <label style={labelStyle}>
        Trade date
        <input name="trade_date" type="date" value={form.trade_date} onChange={handleChange} />
      </label>
    </div>

    <div style={{ border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-md)", padding: "var(--space-md)" }}>
      <p style={{ fontFamily: "var(--font-serif)", fontSize: "var(--text-lg)", margin: "0 0 var(--space-sm)", color: "var(--color-text-primary)" }}>
        What's your reasoning?
      </p>
      <textarea name="thesis_text" value={form.thesis_text} onChange={handleChange} placeholder="Why are you making this trade?" style={{ width: "100%", minHeight: "70px" }} />

      <div style={{ marginTop: "var(--space-sm)" }}>
        <label style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)", display: "block", marginBottom: "6px" }}>
          How confident are you?
        </label>
        <div style={{ display: "flex", gap: "6px" }}>
          {[1, 2, 3, 4, 5].map((score) => (
            <button
              key={score}
              type="button"
              onClick={() => handleConvictionClick(score)}
              style={{
                width: "36px",
                padding: "6px 0",
                fontSize: "var(--text-sm)",
                fontWeight: form.conviction_score === score ? "var(--font-weight-medium)" : "var(--font-weight-normal)",
                background: "transparent",
                color: "var(--color-text-primary)",
                border: form.conviction_score === score ? "1px solid var(--color-text-primary)" : "1px solid var(--color-border-strong)",
                borderRadius: "var(--radius-sm)",
                cursor: "pointer",
              }}
            >
              {score}
            </button>
          ))}
        </div>
      </div>

      <label style={{ ...labelStyle, marginTop: "var(--space-sm)" }}>
        Review date
        <input name="review_date" type="date" value={form.review_date} onChange={handleChange} />
        <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
          We'll ask you to revisit this thesis on this date
        </span>
      </label>
    </div>

    <button
      type="submit"
      style={{
        background: "var(--color-fill-primary)",
        color: "var(--color-on-primary)",
        border: "none",
        borderRadius: "var(--radius-sm)",
        padding: "0.6rem",
        fontWeight: "var(--font-weight-medium)",
        cursor: "pointer",
      }}
    >
      Log trade
    </button>

    {status === "success" && <p style={{ color: "var(--color-success)" }}>Trade logged successfully.</p>}
    {status === "error" && <p style={{ color: "var(--color-danger)" }}>{errorMessage}</p>}
  </form>
)
}

export default TradeForm