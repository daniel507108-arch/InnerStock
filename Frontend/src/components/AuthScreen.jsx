import { useState } from "react"
import { apiFetch } from "../api"

function AuthScreen({ onLogin }) {
  const [mode, setMode] = useState("login") // "login" or "signup"
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const response = await apiFetch(`/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || `Failed to ${mode}`)
      }

      const data = await response.json()
      onLogin(data.token) // hand the new token up to App.jsx
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
      <form
        onSubmit={handleSubmit}
        style={{ background: "var(--color-surface)", padding: "var(--space-lg)", borderRadius: "var(--radius-md)", width: "320px", display: "flex", flexDirection: "column", gap: "var(--space-sm)" }}
      >
        <h2 style={{ margin: "0 0 var(--space-sm)", fontFamily: "var(--font-serif)" }}>
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h2>

        <label style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required style={{ width: "100%" }} />
        </label>

        <label style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required style={{ width: "100%" }} />
        </label>

        {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)" }}>{error}</p>}

        <button
          type="submit"
          disabled={loading}
          style={{ background: "var(--color-fill-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius-sm)", padding: "0.6rem", fontWeight: "var(--font-weight-medium)", cursor: "pointer" }}
        >
          {loading ? "Please wait..." : mode === "login" ? "Log in" : "Sign up"}
        </button>

        <p style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)", textAlign: "center", margin: 0 }}>
          {mode === "login" ? "Don't have an account?" : "Already have an account?"}{" "}
          <span
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
            style={{ color: "var(--color-text-primary)", textDecoration: "underline", cursor: "pointer" }}
          >
            {mode === "login" ? "Sign up" : "Log in"}
          </span>
        </p>
      </form>
    </div>
  )
}

export default AuthScreen