import { useState, useEffect, useRef } from "react"
import { apiFetch } from "../api"
import { IconSend, IconMessageCircle } from "@tabler/icons-react"

function ChatScreen() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  // Used to auto-scroll to the latest message whenever the list changes.
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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || sending) return

    // Show the user's message immediately, before the backend responds -
    // makes the chat feel responsive instead of waiting on the network.
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

  const bubbleBase = {
    maxWidth: "75%",
    padding: "0.6rem 0.9rem",
    borderRadius: "var(--radius-md)",
    fontSize: "var(--text-base)",
    lineHeight: 1.5,
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 100px)", maxWidth: "680px", margin: "0 auto" }}>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.6rem", padding: "1rem 0" }}>
        {loading && <p style={{ color: "var(--color-text-secondary)" }}>Loading conversation...</p>}

        {!loading && messages.length === 0 && (
          <div style={{ textAlign: "center", color: "var(--color-text-secondary)", marginTop: "40px" }}>
            <IconMessageCircle size={28} style={{ marginBottom: "8px" }} />
            <p>Ask about your holdings, your trading patterns, or a specific past trade.</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              ...bubbleBase,
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background: m.role === "user" ? "var(--color-fill-primary)" : "var(--color-surface)",
              color: m.role === "user" ? "var(--color-on-primary)" : "var(--color-text-primary)",
              whiteSpace: "pre-wrap",
            }}
          >
            {m.content}
          </div>
        ))}

        {sending && (
          <div style={{ alignSelf: "flex-start", color: "var(--color-text-muted)", fontSize: "var(--text-sm)", padding: "0.4rem 0.9rem" }}>
            Thinking...
          </div>
        )}

        {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} style={{ display: "flex", gap: "0.5rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.75rem" }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your holdings, patterns, or a past trade"
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          disabled={sending}
          style={{
            width: "38px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--color-fill-primary)",
            color: "var(--color-on-primary)",
            border: "none",
            borderRadius: "var(--radius-sm)",
            cursor: sending ? "default" : "pointer",
            opacity: sending ? 0.6 : 1,
          }}
        >
          <IconSend size={16} />
        </button>
      </form>
    </div>
  )
}

export default ChatScreen