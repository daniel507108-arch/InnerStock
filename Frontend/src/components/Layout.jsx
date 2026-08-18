import {
  IconLayoutDashboard,
  IconPlus,
  IconClock,
  IconChartBar,
  IconMessageCircle,
} from "@tabler/icons-react"

// One nav row. Pure presentation — active state and the click handler are
// both owned by the parent, this component just renders what it's told.
function NavItem({ label, active, onClick, icon }) {
  return (
    <div
      onClick={onClick}
      className={`nav-item${active ? " active" : ""}`}
    >
      {icon}
      {label}
    </div>
  )
}

// Sidebar shell, replacing the old horizontal top nav. Every view
// (Dashboard, TradeForm, ThesisReview, ChatScreen) renders inside
// `.main` and is responsible for its OWN topbar/content — Layout only
// owns the parts that are identical on every screen: the brand mark,
// the four nav items, and the logout control.
function Layout({ activeView, onNavigate, onLogout, children }) {
  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="brand">
          <div className="brand-mark" />
          <span className="brand-name">InnerStock</span>
        </div>

        <nav className="nav">
          <NavItem
            label="Dashboard"
            active={activeView === "dashboard"}
            onClick={() => onNavigate("dashboard")}
            icon={<IconLayoutDashboard size={17} />}
          />
          <NavItem
            label="Log trade"
            active={activeView === "logtrade"}
            onClick={() => onNavigate("logtrade")}
            icon={<IconPlus size={17} />}
          />
          <NavItem
            label="Thesis review"
            active={activeView === "thesisreview"}
            onClick={() => onNavigate("thesisreview")}
            icon={<IconClock size={17} />}
          />
          <NavItem
            label="Advisor"
            active={activeView === "advisor"}
            onClick={() => onNavigate("advisor")}
            icon={<IconMessageCircle size={17} />}
          />
        </nav>

        {/* margin-top: auto (set on .nav-footer in theme.css) pins this to
            the bottom of the sidebar regardless of how many nav items exist
            above it, the same trick used for a sticky footer. */}
        <div className="nav-footer">
          <div className="user-chip">
            <div className="avatar">
              <IconChartBar size={13} />
            </div>
            <button
              onClick={onLogout}
              style={{
                background: "transparent",
                border: "none",
                color: "inherit",
                font: "inherit",
                cursor: "pointer",
                padding: 0,
              }}
            >
              Log out
            </button>
          </div>
        </div>
      </div>

      <div className="main">{children}</div>
    </div>
  )
}

export default Layout