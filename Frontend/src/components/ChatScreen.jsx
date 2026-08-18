import { useState, useEffect, useRef } from "react"
import { apiFetch } from "../api"
import ReactMarkdown from "react-markdown"
import { IconSend, IconMessageCircle, IconChartBar, IconClock } from "@tabler/icons-react"

// Small icon-shaped SVG for the "risk/goals" chip — no matching tabler
// icon felt right for "profile," so this is a plain inline SVG instead
// of pulling in a whole new icon just for one chip.
function IconProfile(props) {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" {...props}>
      <path d="M12 2 2 7l10 5 10-5-10-5Z" />
      <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
    </svg>
  )
}

function ChatScreen() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  // NEW — the grounding strip's data. Fetched once on mount, same three
  // endpoints Dashboard already uses, so the strip can show *real* numbers
  // ("grounded in 5 holdings, $48.2k, 67% accuracy") instead of vague
  // marketing copy. This isn't decoration: build_advisor_context() on the
  // backend genuinely does inject profile + holdings + trading-patterns +
  // recent trades into every /chat call's system prompt — confirmed by
  // reading main.py directly, which resolves the open "is grounding real
  // or a bare pass-through" question flagged in the project blueprint.
  // The chips are an honest reflection of what the advisor is actually
  // using, not an unverified claim.
  const [profile, setProfile] = useState(null)
  const [holdings, setHoldings] = useState(null)
  const [patterns, setPatterns] = useState(null)

  const bottomRef = useRef(null)

  useEffect(() => {
    apiFetch("/chat/history")
      .then((response) => response.json())
      .then((data) => {
        setMessages(data.messages)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    apiFetch("/profile")
      .then((response) => (response.ok ? response.json() : null))
      .then(setProfile)
      .catch(() => setProfile(null))

    apiFetch("/holdings")
      .then((response) => (response.ok ? response.json() : null))
      .then(setHoldings)
      .catch(() => setHoldings(null))

    apiFetch("/trading-patterns")
      .then((response) => (response.ok ? response.json() : null))
      .then((result) => {
        if (!result || result.reviewed_count === 0) return
        const totalCorrect = result.by_conviction.reduce((sum, b) => sum + b.correct, 0)
        setPatterns({ accuracyPercent: (totalCorrect / result.reviewed_count) * 100 })
      })
      .catch(() => setPatterns(null))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, sending])

  async function handleSend(e) {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || sending) return

    setMessages((prev) => [...prev, { role: "user", content: trimmed }])
    setInput("")
    setSending(true)
    setError(null)

    try {
      const response = await apiFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      })

      if (!response.ok) throw new Error("Couldn't reach the advisor")

      const data = await response.json()
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }])
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Advisor</h1>
          <div className="sub">Grounded in your profile, holdings &amp; trade history</div>
        </div>
      </div>

      <div className="content">
        <div className="chat-page">
          <div className="chat-wrap">
            {/* Only renders chips for data that actually loaded — a chip
                claiming context it doesn't have would be worse than no
                chip at all. */}
            {(profile || holdings || patterns) && (
              <div className="grounding-strip">
                <span className="label">Context:</span>
                {profile && (
                  <span className="chip">
                    <IconProfile /> {profile.risk_tolerance} risk · {profile.investing_goals}
                  </span>
                )}
                {holdings && (
                  <span className="chip">
                    <IconChartBar size={12} />
                    {holdings.position_count} holding{holdings.position_count === 1 ? "" : "s"}, $
                    {holdings.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                )}
                {patterns && (
                  <span className="chip">
                    <IconClock size={12} /> {patterns.accuracyPercent.toFixed(0)}% thesis accuracy
                  </span>
                )}
              </div>
            )}

            <div className="chat-thread">
              {loading && <p style={{ color: "var(--color-text-secondary)" }}>Loading conversation...</p>}

              {!loading && messages.length === 0 && (
                <div className="chat-empty">
                  <IconMessageCircle size={28} />
                  <p>Ask about your holdings, your trading patterns, or a specific past trade.</p>
                </div>
              )}

              {messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="msg user">{m.content}</div>
                ) : (
                  // Assistant replies are rendered as Markdown, not plain text.
                  // The backend's system prompt explicitly instructs Claude to
                  // "use Markdown naturally" (headings, bullet points, bold),
                  // but the previous version rendered raw text with
                  // white-space: pre-wrap — so a reply like "**For your
                  // portfolio**" showed up as literal asterisks instead of
                  // bold text. react-markdown parses it into real elements,
                  // styled to fit inside a chat bubble via the .msg.assistant
                  // rules in theme.css.
                  <div key={i} className="msg assistant">
                    <ReactMarkdown>{m.content}</ReactMarkdown>
                  </div>
                )
              )}

              {sending && (
                <div className="typing">
                  <span /><span /><span />
                </div>
              )}

              {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

              <div ref={bottomRef} />
            </div>

            <form onSubmit={handleSend} className="chat-input-bar">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your portfolio, a ticker, or your trading patterns…"
              />
              <button type="submit" disabled={sending} className="btn btn-accent">
                <IconSend size={16} />
              </button>
            </form>
          </div>

          <div className="chat-disclaimer">
            InnerStock Advisor references your logged data, not real-time market execution. Not financial advice.
          </div>
        </div>
      </div>
    </>
  )
}

export default ChatScreen
