function NavItem({ label, active, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "6px 12px",
        borderRadius: "var(--radius-sm)",
        fontSize: "13px",
        fontWeight: active ? 500 : 400,
        background: active ? "var(--color-surface)" : "transparent",
        color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
        cursor: "pointer",
      }}
    >
      {label}
    </div>
  )
}

function Layout({ activeView, onNavigate, children }) {
  return (
    <div style={{ background: "var(--color-bg)", minHeight: "100vh", color: "var(--color-text-primary)" }}>
      <nav style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", borderBottom: "1px solid var(--color-border)" }}>
        <span style={{ fontWeight: 500, fontSize: "15px" }}>InnerStock</span>
        <div style={{ display: "flex", gap: "4px" }}>
          <NavItem label="Dashboard" active={activeView === "dashboard"} onClick={() => onNavigate("dashboard")} />
          <NavItem label="Log trade" active={activeView === "logtrade"} onClick={() => onNavigate("logtrade")} />
          <NavItem label="Thesis review" active={activeView === "thesisreview"} onClick={() => onNavigate("thesisreview")} />
        </div>
      </nav>
      <main style={{ padding: "20px" }}>
        {children}
      </main>
    </div>
  )
}

export default Layout