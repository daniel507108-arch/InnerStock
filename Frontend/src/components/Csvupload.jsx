import { useState } from "react"

function CsvUpload() {
  // Holds the actual file the user picked, or null if nothing's picked yet.
  const [file, setFile] = useState(null)

  // Holds the backend's response after an upload attempt.
  const [results, setResults] = useState(null)

  function handleFileChange(e) {
    setFile(e.target.files[0])
  }

  async function handleUpload() {
    if (!file) return

    const formData = new FormData()
    formData.append("file", file)

    try {
      const response = await fetch("http://127.0.0.1:8000/trades/import", {
        method: "POST",
        body: formData,
      })

      // Check whether the backend considered this a success BEFORE trusting
      // the shape of what it sent back.
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Something went wrong importing this file.")
      }

      const data = await response.json()
      setResults(data)
    } catch (err) {
      setResults({ successful_count: 0, errors: [{ row: "-", message: err.message }] })
    }
  }

  return (
    <div style={{ marginTop: "2rem" }}>
      <h3>Import Trades from CSV</h3>
      <input type="file" accept=".csv" onChange={handleFileChange} />
      <button onClick={handleUpload}>Import CSV</button>

      {results && (
        <div style={{ marginTop: "1rem" }}>
          <p>{results.successful_count} trades imported successfully.</p>
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