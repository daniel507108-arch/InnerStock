import { useEffect, useRef, useState } from "react"
import { apiFetch } from "../api"

// While the dashboard is open, re-sync with the brokerage this often so a
// trade made in Wealthsimple shows up without a reload. The backend skips
// syncs closer together than its own MIN_SYNC_INTERVAL (snaptrade_sync.py),
// so this can't hammer SnapTrade even with several tabs open.
const SYNC_INTERVAL_MS = 5 * 60_000

function timeAgo(isoString) {
  if (!isoString) return "never"
  const minutes = Math.round((Date.now() - new Date(isoString).getTime()) / 60_000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.round(hours / 24)} days ago`
}

function describeSync(result) {
  const imported = result.new_trades + result.matched_existing
  if (result.errors?.length) return { text: result.errors.join(" · "), isError: true }
  if (imported === 0) return { text: "Up to date - no new trades.", isError: false }
  return { text: `${imported} trade${imported === 1 ? "" : "s"} synced from your brokerage.`, isError: false }
}

// Linked-brokerage strip on the dashboard: shows which brokerage accounts
// are syncing and when they last synced, keeps them synced in the
// background, and offers "Sync now", "Connect account" and (with developer
// SnapTrade keys, where each user has their own link) "Disconnect".
// Renders nothing when brokerage sync isn't available to this user (GET
// /brokerage/status says available: false) - e.g. with a personal key,
// everyone except its owner.
//
// onSynced is called whenever a sync actually brought in or updated trades,
// so the dashboard can reload holdings.
function BrokerageCard({ onSynced }) {
  const [status, setStatus] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState(null)
  // Kept in a ref so the background interval always calls the latest
  // callback without re-creating the interval when the parent re-renders.
  const onSyncedRef = useRef(onSynced)
  useEffect(() => {
    onSyncedRef.current = onSynced
  }, [onSynced])

  async function runSync(force) {
    setSyncing(true)
    try {
      const response = await apiFetch(`/brokerage/sync?force=${force}`, { method: "POST" })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.detail || "Sync failed")

      setStatus((prev) => ({ ...prev, ...result }))
      if (result.new_trades > 0 || result.matched_existing > 0) onSyncedRef.current?.()
      // Background syncs stay quiet unless something happened; a manual
      // "Sync now" always reports back.
      if (!result.skipped_recent_sync && (force || result.new_trades > 0 || result.errors?.length)) {
        setMessage(describeSync(result))
      }
    } catch (err) {
      setMessage({ text: err.message, isError: true })
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    let intervalId = null

    apiFetch("/brokerage/status")
      .then((response) => (response.ok ? response.json() : { available: false }))
      .then((result) => {
        if (cancelled) return
        setStatus(result)
        if (!result.available) return
        runSync(false)
        intervalId = setInterval(() => runSync(false), SYNC_INTERVAL_MS)
      })
      .catch(() => {
        if (!cancelled) setStatus({ available: false })
      })

    return () => {
      cancelled = true
      if (intervalId) clearInterval(intervalId)
    }
  }, [])

  async function handleConnect() {
    // Open the tab synchronously (inside the click) so popup blockers allow
    // it, then point it at the one-time SnapTrade link once it arrives.
    const portal = window.open("", "_blank")
    try {
      const response = await apiFetch("/brokerage/connect", { method: "POST" })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.detail || "Could not start a connection")
      if (portal) portal.location.href = result.redirect_uri
      else window.location.href = result.redirect_uri
      setMessage({ text: "Finish connecting in the new tab, then press Sync now.", isError: false })
    } catch (err) {
      portal?.close()
      setMessage({ text: err.message, isError: true })
    }
  }

  async function handleDisconnect() {
    const ok = window.confirm(
      "Disconnect your brokerage? SnapTrade will delete its connection and data for you. " +
      "Trades already in InnerStock (and your theses) are kept."
    )
    if (!ok) return
    try {
      const response = await apiFetch("/brokerage/connection", { method: "DELETE" })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.detail || "Could not disconnect")
      setStatus(result)
      setMessage({ text: "Brokerage disconnected. Your trades are still here.", isError: false })
    } catch (err) {
      setMessage({ text: err.message, isError: true })
    }
  }

  if (!status?.available) return null

  const accounts = status.accounts_detail || []
  const syncedAccounts = accounts.filter((a) => a.sync_enabled)
  // With developer keys a user may link any brokerage SnapTrade supports,
  // so the name comes from the linked accounts rather than being fixed.
  const brokerName = accounts[0]?.institution || "Brokerage"

  let accountLabel = "Not linked"
  if (status.connected) {
    accountLabel = syncedAccounts.length
      ? syncedAccounts.map((a) => a.account_type?.toUpperCase()).join(" · ")
      : "No accounts syncing"
  }

  let meta = "Link your Wealthsimple to sync trades automatically"
  if (syncing) meta = "Syncing…"
  else if (status.connected) meta = `Synced ${timeAgo(status.last_synced_at)}`

  return (
    <div className="brokerage-card">
      <div className="brokerage-info">
        <span className="brokerage-name">{brokerName}</span>
        <span className="pill pill-muted">{accountLabel}</span>
        <span className="brokerage-meta">{meta}</span>
      </div>
      <div className="brokerage-actions">
        <button className="btn" onClick={() => runSync(true)} disabled={syncing}>
          Sync now
        </button>
        <button className={status.connected ? "btn" : "btn btn-accent"} onClick={handleConnect}>
          {status.connected ? "Reconnect" : "Connect account"}
        </button>
        {status.can_disconnect && (
          <button className="btn" onClick={handleDisconnect}>
            Disconnect
          </button>
        )}
      </div>
      {message && (
        <div className={`brokerage-message${message.isError ? " error" : ""}`}>{message.text}</div>
      )}
    </div>
  )
}

export default BrokerageCard
