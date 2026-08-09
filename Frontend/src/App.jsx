import { useState } from 'react'
import Layout from './components/Layout'
import AuthScreen from './components/AuthScreen'
import TradeForm from './components/TradeForm'
import CsvUpload from './components/CsvUpload'
import Dashboard from './components/Dashboard'
import ThesisReview from './components/ThesisReview'

function App() {
  const [token, setToken] = useState(localStorage.getItem("token"))
  const [refreshKey, setRefreshKey] = useState(0)
  const [activeView, setActiveView] = useState('dashboard')

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

  // Not logged in — show the auth screen instead of the app entirely.
  if (!token) {
    return <AuthScreen onLogin={handleLogin} />
  }

  return (
    <Layout activeView={activeView} onNavigate={setActiveView} onLogout={handleLogout}>
      {activeView === 'dashboard' && <Dashboard refreshKey={refreshKey} />}

      {activeView === 'logtrade' && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-lg)", maxWidth: "440px", margin: "0 auto" }}>
          <TradeForm onTradeLogged={handleTradeLogged} />
          <CsvUpload onTradeLogged={handleTradeLogged} />
        </div>
      )}

      {activeView === 'thesisreview' && <ThesisReview />}
    </Layout>
  )
}

export default App