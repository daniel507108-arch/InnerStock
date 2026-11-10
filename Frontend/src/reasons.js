// Shared helpers for trade reasons (see components/ReasonChips.jsx and the
// backend's thesis.py, which owns the actual list of reasons).

// The honest "I can't say why I made this trade" answer. Exclusive with
// every other reason, and the only answer that doesn't need a thesis.
export const DONT_REMEMBER = "dont_remember"

// Quick review-date choices: when should this trade come back for grading?
export const REVIEW_OPTIONS = [
  { key: "1m", label: "1 month", months: 1 },
  { key: "3m", label: "3 months", months: 3 },
  { key: "6m", label: "6 months", months: 6 },
  { key: "1y", label: "1 year", months: 12 },
]

// YYYY-MM-DD, `months` from today (local date, like the date inputs use).
export function dateMonthsFromToday(months) {
  const d = new Date()
  d.setMonth(d.getMonth() + months)
  const pad = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
