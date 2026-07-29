import { useState } from 'react'
import Layout from './components/Layout'
import TradeForm from './components/TradeForm'
import CsvUpload from './components/CsvUpload'
import HoldingsTable from './components/HoldingsTable'
import ThesisReview from './components/ThesisReview'

function App() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [activeView, setActiveView] = useState('dashboard')

  function handleTradeLogged() {
    setRefreshKey((prev) => prev + 1)
  }

  return (
    <Layout activeView={activeView} onNavigate={setActiveView}>
      {activeView === 'dashboard' && (
        <HoldingsTable refreshKey={refreshKey} />
      )}

      {activeView === 'logtrade' && (
        <>
          <TradeForm onTradeLogged={handleTradeLogged} />
          <CsvUpload onTradeLogged={handleTradeLogged} />
        </>
      )}

      {activeView === 'thesisreview' && (
        <ThesisReview />
      )}
    </Layout>
  )
}

export default App