const API_BASE = "http://127.0.0.1:8000"

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