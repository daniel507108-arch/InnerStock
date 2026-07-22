// useState: lets a component "remember" a value and re-display automatically when it changes
// useEffect: lets us run code at a specific moment (here: right when the page first loads)
import { useState, useEffect } from 'react'
import TradeForm from './components/TradeForm'
import CsvUpload from "./components/CsvUpload"
import HoldingsTable from "./components/HoldingsTable"
import ThesisReview from './components/ThesisReview'

function App() {
  // Create a piece of data called "message", starting as "Loading..."
  // setMessage is the function we call whenever we want to change it
  const [message, setMessage] = useState('Loading...')

  // A simple counter. Its actual number means nothing — the only thing
  // that matters is that it CHANGES, which is what triggers a re-fetch.
  const [refreshKey, setRefreshKey] = useState(0)

  // Called by TradeForm or CsvUpload whenever a trade successfully saves.
  function handleTradeLogged() {
    setRefreshKey((prev) => prev + 1)
  }

  // useEffect with an empty array [] at the end means:
  // "run this code once, right when the page first appears"
  useEffect(() => {
    // fetch() sends a request to the given address and waits for a response
    fetch('http://127.0.0.1:8000/test')
      .then(response => response.json())     // convert the raw response into usable data
      .then(data => setMessage(data.data))    // grab the "data" field and store it in our message
      .catch(error => setMessage('Failed to connect: ' + error.message)) // if something goes wrong, show why
  }, [])

  // This is what actually gets displayed on the page.
  // {message} inserts whatever the current value of "message" is.
  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>InnerStock</h1>
      <p>Backend says: {message}</p>
      <TradeForm onTradeLogged={handleTradeLogged} />
      <CsvUpload onTradeLogged={handleTradeLogged} />
      <HoldingsTable refreshKey={refreshKey} />
      <ThesisReview />
    </div>
  )
}

export default App
// --- Reference for later: what a POST request (sending data, not just fetching) looks like ---
// fetch('http://127.0.0.1:8000/trades', {
//   method: 'POST',
//   headers: { 'Content-Type': 'application/json' },
//   body: JSON.stringify({ ticker: 'AAPL', shares: 10 })
// })