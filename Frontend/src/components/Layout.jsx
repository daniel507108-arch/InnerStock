import {
  IconLayoutDashboard,
  IconPlus,
  IconClock,
  IconChartBar,
  IconMessageCircle,
  IconSearch,
  IconSettings,
} from "@tabler/icons-react"
import SidebarWatchlist from "./SidebarWatchlist"

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
function Layout({ activeView, onNavigate, onLogout, onChangeContext, children }) {
  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="brand">
          <div className="brand-mark" />
          <span className="brand-name">InnerStock</span>
        </div>
        <nav className="nav">
          <NavItem label="Dashboard" active={activeView === "dashboard"} onClick={() => onNavigate("dashboard")} icon={<IconLayoutDashboard size={16} />} />
          <NavItem label="Log trade" active={activeView === "logtrade"} onClick={() => onNavigate("logtrade")} icon={<IconPlus size={16} />} />
          <NavItem label="Thesis review" active={activeView === "thesisreview"} onClick={() => onNavigate("thesisreview")} icon={<IconClock size={16} />} />
          <NavItem label="Search" active={activeView === "search"} onClick={() => onNavigate("search")} icon={<IconSearch size={16} />} />
          <NavItem label="Advisor" active={activeView === "advisor"} onClick={() => onNavigate("advisor")} icon={<IconMessageCircle size={16} />} />
        </nav>

        <SidebarWatchlist onNavigate={onNavigate} />

        
        {/* margin-top: auto (set on .nav-footer in theme.css) pins this to
            the bottom of the sidebar regardless of how many nav items exist
            above it, the same trick used for a sticky footer. */}
        <div className="nav-footer">
          {/* Reuses NavItem rather than a one-off button, so this row looks
              and behaves exactly like Dashboard/Log trade/etc. above it -
              including highlighting while the user is actually on that
              screen. Opens SurveyScreen in edit mode (App.jsx wires
              onChangeContext to activeView "editprofile") so previously
              entered survey answers can be revisited and changed. */}
          <NavItem
            label="Change Context"
            active={activeView === "editprofile"}
            onClick={onChangeContext}
            icon={<IconSettings size={17} />}
          />
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