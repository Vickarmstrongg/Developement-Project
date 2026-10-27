import {
  CalendarDays,
  Clock3,
  FileText,
  LayoutDashboard,
  Scale,
  TrendingUp,
  Users
} from "lucide-react";
import logo from "./assets/Logo.png";
import { getStoredUser } from "./api";

const NAV_ITEMS = [
  { id: "dashboard", hash: "#dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "rush", hash: "#rush-hour-radar", label: "Rush Hour Radar", icon: Clock3 },
  { id: "demand", hash: "#demand-forecast", label: "Demand Forecast", icon: TrendingUp },
  { id: "fair", hash: "#fair-comparison", label: "Fair Comparison", icon: Scale },
  { id: "context", hash: "#context-events", label: "Calendar / Context Events", icon: CalendarDays },
  { id: "users", hash: "#users", label: "Users", icon: Users, adminOnly: true },
];

function WorkspaceSidebar({ activeView, onNavigate }) {
    const isAdmin = getStoredUser()?.role === "Admin";
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-name">Byte &amp; Bite</span>
        <img src={logo} alt="Byte & Bite" className="brand-logo" />
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-section">
          <span className="sidebar-title">WORKSPACE</span>
          <nav aria-label="Workspace">
            {NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin).map(({ id, hash, label, icon: Icon }) => (
              <a
                key={id}
                href={hash}
                className={`sidebar-link${activeView === id ? " active" : ""}`}
                aria-current={activeView === id ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  onNavigate(id);
                }}
              >
                <Icon size={16} />
                {label}
              </a>
            ))}
          </nav>
        </div>

        <div className="sidebar-section">
          <span className="sidebar-title">Reporting</span>
          <nav aria-label="Reporting">
            <a
              href="#reports"
              className={`sidebar-link${activeView === "reports" ? " active" : ""}`}
              aria-current={activeView === "reports" ? "page" : undefined}
            >
              <FileText size={16} />
              Reports
            </a>
          </nav>
        </div>
      </div>
    </aside>
  );
}

export default WorkspaceSidebar;
