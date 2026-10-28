import { useEffect, useRef, useState } from "react";
import { Bell, ChevronDown, LogOut, RefreshCw } from "lucide-react";
import { apiFetch } from "./api";
import WorkspaceSidebar from "./WorkspaceSidebar";

// which page each report type belongs to (names used by App.jsx navigation)
const TYPE_TO_VIEW = {
    dashboard: "dashboard",
    rush_hour_radar: "rush",
    demand_forecast: "demand",
    fair_comparison: "fair",
    calendar_events: "context",
};

function formatWhen(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleString("en-ZA", {
              dateStyle: "medium",
              timeStyle: "short",
          });
}

function formatDay(value) {
    if (!value) return "";
    const date = new Date(`${value}T12:00:00`);
    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleDateString("en-ZA", {
              day: "numeric",
              month: "short",
              year: "numeric",
          });
}

function formatPeriod(start, end) {
    if (!start && !end) return "—";
    if (start === end || !end) return formatDay(start);
    return `${formatDay(start)} – ${formatDay(end)}`;
}

function Reports({ currentUser, onNavigate, onLogout }) {
    const [exportsList, setExportsList] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [typeFilter, setTypeFilter] = useState("");
    const [reloadKey, setReloadKey] = useState(0);
    const [profileOpen, setProfileOpen] = useState(false);
    const profileRef = useRef(null);

    const user = currentUser || { name: "", role: "" };

    const heading =
        user.role === "Admin"
            ? "All exports"
            : user.role === "Manager"
              ? "Exports for your businesses"
              : "Your exports";

    useEffect(() => {
        function handleClickOutside(event) {
            if (profileRef.current && !profileRef.current.contains(event.target)) {
                setProfileOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    useEffect(() => {
        const controller = new AbortController();

        async function load() {
            setLoading(true);
            setError("");
            try {
                const response = await apiFetch("/api/reports/exports", {
                    signal: controller.signal,
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(
                        typeof data.detail === "string"
                            ? data.detail
                            : `Could not load reports (${response.status}).`
                    );
                }
                setExportsList(data.exports || []);
            } catch (err) {
                if (err.name !== "AbortError") {
                    setError(err.message || "Could not load reports.");
                }
            } finally {
                if (!controller.signal.aborted) setLoading(false);
            }
        }

        load();
        return () => controller.abort();
    }, [reloadKey]);

    const types = [
        ...new Map(
            exportsList.map((row) => [row.report_type, row.report_label])
        ).entries(),
    ];
    const visible = typeFilter
        ? exportsList.filter((row) => row.report_type === typeFilter)
        : exportsList;

    return (
        <div className="app-layout">
            <WorkspaceSidebar activeView="reports" onNavigate={onNavigate} />

            <main className="main-content">
                <header className="topbar">
                    <div className="breadcrumb">
                        Reporting / <strong>Reports</strong>
                    </div>

                    <div className="topbar-right">
                        <button
                            className="notification-button"
                            onClick={() => (window.location.href = "/notifications")}
                            aria-label="Notifications"
                            title="Notifications"
                        >
                            <Bell size={18} />
                        </button>

                        <div className="profile-container" ref={profileRef}>
                            <button
                                className="user-profile"
                                onClick={() => setProfileOpen((open) => !open)}
                                aria-label="Open user menu"
                            >
                                <div className="user-avatar">
                                    {(user.name || "").charAt(0)}
                                </div>
                                <div className="user-details">
                                    <strong>{user.name}</strong>
                                    <span>{user.role}</span>
                                </div>
                                <ChevronDown size={14} className="profile-chevron" />
                            </button>

                            {profileOpen && (
                                <div className="profile-dropdown">
                                    <button
                                        className="logout-option"
                                        onClick={() => {
                                            setProfileOpen(false);
                                            onLogout();
                                        }}
                                    >
                                        <LogOut size={15} />
                                        Log Out
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                <div className="page-content">
                    <div className="page-heading">
                        <h1>Reports</h1>
                        <p>
                            A record of reports exported from Byte &amp; Bite: who exported what, and when.
                        </p>
                    </div>

                    <section className="panel context-events-panel">
                        <div className="context-events-toolbar">
                            <h2>{heading}</h2>
                            <div className="context-events-controls">
                                <label>
                                    Report
                                    <select
                                        value={typeFilter}
                                        onChange={(e) => setTypeFilter(e.target.value)}
                                    >
                                        <option value="">All reports</option>
                                        {types.map(([value, label]) => (
                                            <option key={value} value={value}>
                                                {label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() => setReloadKey((key) => key + 1)}
                                    disabled={loading}
                                >
                                    <RefreshCw size={14} /> Refresh
                                </button>
                            </div>
                        </div>

                        {error && (
                            <div className="context-events-state" role="alert">
                                {error}
                            </div>
                        )}

                        {loading && !error && (
                            <div className="context-events-state" role="status">
                                Loading reports…
                            </div>
                        )}

                        {!loading && !error && visible.length === 0 && (
                            <div className="context-events-state" role="status">
                                No exports have been recorded yet.
                            </div>
                        )}

                        {!loading && !error && visible.length > 0 && (
                            <div className="context-events-table-wrap">
                                <table className="context-events-table">
                                    <thead>
                                        <tr>
                                            <th align="left">When</th>
                                            <th align="left">Report</th>
                                            <th align="left">Business</th>
                                            <th align="left">Period</th>
                                            <th align="left">Exported by</th>
                                            <th align="left">Preview</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {visible.map((row) => (
                                            <tr key={row.report_id}>
                                                <td>{formatWhen(row.generated_at)}</td>
                                                <td>{row.report_label}</td>
                                                <td>{row.vendor_name || "All businesses"}</td>
                                                <td>
                                                    {formatPeriod(
                                                        row.period_start,
                                                        row.period_end
                                                    )}
                                                </td>
                                                <td>
                                                    {row.generated_by}
                                                    {row.generated_by_role
                                                        ? ` (${row.generated_by_role})`
                                                        : ""}
                                                </td>
                                                <td>
                                                    {TYPE_TO_VIEW[row.report_type] && (
                                                        <button
                                                            type="button"
                                                            className="btn-ghost"
                                                            title="Opens the live page. Figures may have changed since this export."
                                                            onClick={() =>
                                                                onNavigate(
                                                                    TYPE_TO_VIEW[row.report_type]
                                                                )
                                                            }
                                                        >
                                                            Open report
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        <p className="dashboard-data-note">
                            “Open report” shows the live page, so figures may differ
                            from the exported PDF if new data has been loaded since.
                        </p>
                    </section>
                </div>
            </main>
        </div>
    );
}

export default Reports;