import { useState } from "react"

function TradeForm() {
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
    } catch (err) {
      // Covers both backend errors above AND total failures (backend not running, network issue).
      setStatus("error")
      setErrorMessage(err.message)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxWidth: "300px" }}>
      <input name="ticker" value={form.ticker} onChange={handleChange} placeholder="Ticker (e.g. AAPL)" />

      <select name="action" value={form.action} onChange={handleChange}>
        <option value="buy">Buy</option>
        <option value="sell">Sell</option>
      </select>

      <input name="quantity" type="number" value={form.quantity} onChange={handleChange} placeholder="Quantity" />
      <input name="price_per_share" type="number" value={form.price_per_share} onChange={handleChange} placeholder="Price per share" />
      <input name="trade_date" type="date" value={form.trade_date} onChange={handleChange} />
      <textarea name="thesis_text" value={form.thesis_text} onChange={handleChange} placeholder="Why are you making this trade?" />
      <input name="conviction_score" type="number" min="1" max="5" value={form.conviction_score} onChange={handleChange} />
      <input name="review_date" type="date" value={form.review_date} onChange={handleChange} />

      <button type="submit">Log Trade</button>

      {/* Only shows up once status actually changes from null */}
      {status === "success" && <p style={{ color: "green" }}>Trade logged successfully.</p>}
      {status === "error" && <p style={{ color: "red" }}>{errorMessage}</p>}
    </form>
  )
}

export default TradeForm