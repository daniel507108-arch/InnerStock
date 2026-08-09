import { IconLayoutDashboard, IconPlus, IconClock, IconChartBar } from "@tabler/icons-react"


function NavItem({ label, active, onClick, icon }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 12px",
        borderRadius: "var(--radius-sm)",
        fontSize: "13px",
        fontWeight: active ? 500 : 400,
        background: active ? "var(--color-surface)" : "transparent",
        color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
        cursor: "pointer",
      }}
    >
      {icon}
      {label}
    </div>
  )
}

function Layout({ activeView, onNavigate, onLogout, children }) {
  return (
    <div style={{ background: "var(--color-bg)", minHeight: "100vh", color: "var(--color-text-primary)" }}>
      <nav style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", borderBottom: "1px solid var(--color-border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ width: "26px", height: "26px", borderRadius: "7px", background: "var(--color-success-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <IconChartBar size={16} color="var(--color-success)" />
          </div>
          <span style={{ fontWeight: 500, fontSize: "15px" }}>InnerStock</span>
      </div>
        <div style={{ display: "flex", gap: "4px" }}>
          <NavItem label="Dashboard" active={activeView === "dashboard"} onClick={() => onNavigate("dashboard")} icon={<IconLayoutDashboard size={16} />} />
          <NavItem label="Log trade" active={activeView === "logtrade"} onClick={() => onNavigate("logtrade")} icon={<IconPlus size={16} />} />
          <NavItem label="Thesis review" active={activeView === "thesisreview"} onClick={() => onNavigate("thesisreview")} icon={<IconClock size={16} />} />
        </div>
        <button
  onClick={onLogout}
  style={{ background: "transparent", border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-sm)", padding: "0.3rem 0.7rem", color: "var(--color-text-secondary)", fontSize: "var(--text-sm)", cursor: "pointer" }}
>
  Log out
</button>
      </nav>
      <main style={{ padding: "20px" }}>
        {children}
      </main>
    </div>
  )
}

export default Layout