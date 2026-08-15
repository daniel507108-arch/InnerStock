import { useState, useEffect } from 'react'
import Layout from './components/Layout'
import AuthScreen from './components/AuthScreen'
import SurveyScreen from './components/SurveyScreen'
import TradeForm from './components/TradeForm'
import CsvUpload from './components/CsvUpload'
import Dashboard from './components/Dashboard'
import ThesisReview from './components/ThesisReview'
import { apiFetch } from './api'

function App() {
  const [token, setToken] = useState(localStorage.getItem("token"))
  const [refreshKey, setRefreshKey] = useState(0)
  const [activeView, setActiveView] = useState('dashboard')

  // Tracks whether the logged-in user has completed the survey yet.
  // null = still checking, true = has a profile, false = needs the survey.
  const [hasProfile, setHasProfile] = useState(null)

  // Whenever we have a token, check if a profile already exists for this
  // user - this runs once on login/app load, and again after the survey
  // is submitted (via handleSurveyComplete below).
  useEffect(() => {
  if (!token) {
    setHasProfile(null)
    return
  }

  apiFetch("/profile")
    .then((response) => {
      if (response.status === 401) {
        // Token is invalid or points to a user that no longer exists
        // (e.g. after a database reset during testing) - treat this as
        // "not actually logged in" rather than getting stuck showing
        // the survey with a broken identity underneath it.
        localStorage.removeItem("token")
        setToken(null)
        setHasProfile(null)
        return
      }
      setHasProfile(response.ok)
    })
    .catch(() => {
      setHasProfile(false)
    })
}, [token])

  function handleTradeLogged() {
    setRefreshKey((prev) => prev + 1)
  }

  function handleLogin(newToken) {
    localStorage.setItem("token", newToken)
    setToken(newToken)
  }

  function handleLogout() {
    localStorage.removeItem("token")
    setToken(null)
  }

  // Called by SurveyScreen once the profile is successfully submitted -
  // flips hasProfile to true so the app moves on to the real dashboard.
  function handleSurveyComplete() {
    setHasProfile(true)
  }

  // Not logged in — show the auth screen instead of the app entirely.
  if (!token) {
    return <AuthScreen onLogin={handleLogin} />
  }

  // Logged in, but we haven't checked (or finished checking) whether a
  // profile exists yet - avoid flashing the survey or dashboard incorrectly
  // while that request is still in flight.
  if (hasProfile === null) {
    return <p style={{ color: "var(--color-text-secondary)", textAlign: "center", marginTop: "40px" }}>Loading...</p>
  }

  // Logged in, but no profile yet - block access to the rest of the app
  // until the required survey is completed.
  if (!hasProfile) {
    return <SurveyScreen onComplete={handleSurveyComplete} />
  }

  return (
    <Layout activeView={activeView} onNavigate={setActiveView} onLogout={handleLogout}>
      {activeView === 'dashboard' && (
        <Dashboard refreshKey={refreshKey} />
      )}
      {activeView === 'logtrade' && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-lg)", maxWidth: "440px", margin: "0 auto" }}>
          <TradeForm onTradeLogged={handleTradeLogged} />
          <CsvUpload onTradeLogged={handleTradeLogged} />
        </div>
      )}
      {activeView === 'thesisreview' && (
        <ThesisReview />
      )}
    </Layout>
  )
}

export default App