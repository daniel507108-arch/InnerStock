import { useState } from "react"
import { apiFetch } from "../api"

// Upload logic is identical to the current version — same FormData
// construction, same /trades/import POST, same success/error handling.
// Only the returned JSX changes: a bare <input type="file"> + button
// becomes the mockup's dashed drop-zone card, matching the visual
// language the CSV import area uses in the mockup (and echoing the same
// dashed-border treatment .reasoning-card uses in TradeForm, so the two
// "secondary" panels on this tab read as a matched pair).
function CsvUpload({ onTradeLogged }) {
  const [file, setFile] = useState(null)
  const [results, setResults] = useState(null)

  function handleFileChange(e) {
    setFile(e.target.files[0])
  }

  async function handleUpload() {
    if (!file) return

    const formData = new FormData()
    formData.append("file", file)

    try {
      const response = await apiFetch("/trades/import", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Something went wrong importing this file.")
      }

      const data = await response.json()
      setResults(data)
      if (data.successful_count > 0) {
        onTradeLogged()
      }
    } catch (err) {
      setResults({ successful_count: 0, errors: [{ row: "-", message: err.message }] })
    }
  }

  return (
    <div className="csv-drop">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <path d="M17 8l-5-5-5 5" />
        <path d="M12 3v12" />
      </svg>
      <div style={{ marginBottom: "var(--space-sm)" }}>Bulk-import trades from a CSV file</div>

      <input type="file" accept=".csv" onChange={handleFileChange} />

      <div style={{ marginTop: "var(--space-sm)" }}>
        <button onClick={handleUpload} className="btn" disabled={!file}>
          Import CSV
        </button>
      </div>

      {results && (
        <div className="csv-results">
          <p style={{ color: "var(--color-text-primary)", margin: 0 }}>
            {results.successful_count} trade{results.successful_count === 1 ? "" : "s"} imported successfully.
          </p>
          {results.errors?.length > 0 && (
            <ul>
              {results.errors.map((err, i) => (
                <li key={i}>Row {err.row}: {err.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default CsvUpload
