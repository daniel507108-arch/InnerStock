// Backend address. Local dev talks to uvicorn on 127.0.0.1:8000; a deployed
// build (e.g. on Vercel) sets VITE_API_URL to the hosted backend instead.
// Vite bakes VITE_* variables in at build time, so changing it means
// rebuilding/redeploying the frontend.
const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")

// Every component should call this instead of fetch() directly.
// It automatically attaches the auth token, and centralizes the
// base URL so it only needs to change in one place if it ever does.
export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("token")

  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  return fetch(`${API_BASE}${path}`, { ...options, headers })
}
