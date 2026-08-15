import { useState } from "react"
import { apiFetch } from "../api"

// Each question's options as [value, label] pairs - value is what gets sent
// to the backend, label is what the user sees.
const QUESTIONS = [
  {
    key: "risk_tolerance",
    label: "How much investment risk are you comfortable with?",
    options: [
      ["low", "Low - I prefer stability over big gains"],
      ["medium", "Medium - I can handle some ups and downs"],
      ["high", "High - I'm comfortable with significant volatility"],
    ],
  },
  {
    key: "investing_goals",
    label: "What's your primary investing goal?",
    options: [
      ["growth", "Long-term growth"],
      ["income", "Generating income"],
      ["preservation", "Preserving capital"],
      ["speculation", "Speculation / high-risk opportunities"],
    ],
  },
  {
    key: "trading_style",
    label: "How would you describe your trading style?",
    options: [
      ["buy_and_hold", "Buy and hold"],
      ["active", "Active trading"],
      ["swing", "Swing trading"],
    ],
  },
  {
    key: "time_horizon",
    label: "What's your typical investing time horizon?",
    options: [
      ["under_1y", "Under 1 year"],
      ["1_to_5y", "1 to 5 years"],
      ["5y_plus", "5+ years"],
    ],
  },
  {
    key: "income_bracket",
    label: "What's your approximate annual income?",
    options: [
      ["under_50k", "Under $50k"],
      ["50k_100k", "$50k - $100k"],
      ["100k_plus", "$100k+"],
    ],
  },
  {
    key: "experience_level",
    label: "How would you describe your investing experience?",
    options: [
      ["beginner", "Beginner"],
      ["intermediate", "Intermediate"],
      ["experienced", "Experienced"],
    ],
  },
]

const SECTOR_OPTIONS = [
  "tech", "healthcare", "energy", "financials", "consumer", "industrials", "real_estate",
]

function SurveyScreen({ onComplete }) {
  // One object holding every answer, keyed by question key - same pattern
  // TradeForm uses for its own form state.
  const [answers, setAnswers] = useState({
    risk_tolerance: "",
    investing_goals: "",
    trading_style: "",
    time_horizon: "",
    income_bracket: "",
    experience_level: "",
  })
  const [sectors, setSectors] = useState([])
  const [biggestFear, setBiggestFear] = useState("")
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function handleAnswer(key, value) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  function toggleSector(sector) {
    setSectors((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]
    )
  }

  // Checks every required (multiple-choice) field has an answer before
  // allowing submission - the free-text field and sectors are intentionally
  // excluded, since those are optional per the product decision to never
  // block someone on a field they might not want to answer.
  function validate() {
    for (const q of QUESTIONS) {
      if (!answers[q.key]) return `Please answer: "${q.label}"`
    }
    if (sectors.length === 0) return "Please select at least one sector of interest."
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const response = await apiFetch("/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...answers,
          sectors_of_interest: sectors,
          // Send null rather than an empty string when left blank - matches
          // the backend's Optional[str] = None expectation, though either
          // is accepted without error.
          biggest_fear: biggestFear.trim() || null,
        }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || "Failed to save your profile")
      }

      onComplete() // tell App.jsx the survey is done, move on to the dashboard
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const labelStyle = {
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
    fontSize: "var(--text-sm)",
    color: "var(--color-text-primary)",
    marginBottom: "var(--space-md)",
  }

  const optionButtonStyle = (selected) => ({
    background: selected ? "var(--color-fill-primary)" : "transparent",
    color: selected ? "var(--color-on-primary)" : "var(--color-text-primary)",
    border: "1px solid var(--color-border-strong)",
    borderRadius: "var(--radius-sm)",
    padding: "0.45rem 0.8rem",
    marginRight: "0.5rem",
    marginBottom: "0.4rem",
    cursor: "pointer",
    fontSize: "var(--text-sm)",
  })

  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "40px 20px" }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: "var(--color-surface)",
          padding: "var(--space-lg)",
          borderRadius: "var(--radius-md)",
          width: "100%",
          maxWidth: "480px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-serif)" }}>
          Tell us about your investing style
        </h2>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)", marginTop: 0, marginBottom: "var(--space-lg)" }}>
          This helps InnerStock give you analysis that actually fits how you invest.
        </p>

        {QUESTIONS.map((q) => (
          <label key={q.key} style={labelStyle}>
            {q.label}
            <div>
              {q.options.map(([value, optLabel]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => handleAnswer(q.key, value)}
                  style={optionButtonStyle(answers[q.key] === value)}
                >
                  {optLabel}
                </button>
              ))}
            </div>
          </label>
        ))}

        <label style={labelStyle}>
          Which sectors are you most interested in? (select all that apply)
          <div>
            {SECTOR_OPTIONS.map((sector) => (
              <button
                key={sector}
                type="button"
                onClick={() => toggleSector(sector)}
                style={optionButtonStyle(sectors.includes(sector))}
              >
                {sector.replace("_", " ")}
              </button>
            ))}
          </div>
        </label>

        <label style={labelStyle}>
          What's a mistake or fear you have around investing? (optional)
          <textarea
            value={biggestFear}
            onChange={(e) => setBiggestFear(e.target.value)}
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </label>

        {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          style={{
            background: "var(--color-fill-primary)",
            color: "var(--color-on-primary)",
            border: "none",
            borderRadius: "var(--radius-sm)",
            padding: "0.6rem",
            fontWeight: "var(--font-weight-medium)",
            cursor: submitting ? "default" : "pointer",
            opacity: submitting ? 0.6 : 1,
            marginTop: "var(--space-sm)",
          }}
        >
          {submitting ? "Saving..." : "Continue to dashboard"}
        </button>
      </form>
    </div>
  )
}

export default SurveyScreen