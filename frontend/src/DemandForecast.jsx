import { useEffect, useRef, useState } from "react";
import { apiFetch, getStoredUser } from "./api";

import {
    Bell,
    LogOut,
    ChevronDown,
    CalendarDays,
    ArrowLeft,
    ArrowUp,
    ArrowDown,
    X,
} from "lucide-react";

import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import ReportButton from "./ReportButton";
import WorkspaceSidebar from "./WorkspaceSidebar";
import UsersLink from "./UsersLink";

function formatNumber(value) {
    return Number(value ?? 0).toFixed(2);
}

function formatRand(value) {
    if (value == null || value === "") return "N/A";

    const totalCents = Math.round(Number(value) * 100);
    const whole = Math.floor(totalCents / 100);
    const cents = totalCents % 100;

    const formattedWhole = new Intl.NumberFormat("en-US", {
        useGrouping: true,
        maximumFractionDigits: 0,
    })
        .format(whole)
        .split(",")
        .join(" ");

    return `R ${formattedWhole}.${String(cents).padStart(2, "0")}`;
}


function formatComparisonPeriod(startDate, endDate) {
    if (!startDate || !endDate) return "Dates unavailable";

    const start = new Date(`${startDate}T12:00:00`);
    const end = new Date(`${endDate}T12:00:00`);

    const startDay = start.getDate();
    const endDay = end.getDate();

    const startMonth = start.toLocaleDateString("en-ZA", {
        month: "short",
    });

    const endMonth = end.toLocaleDateString("en-ZA", {
        month: "short",
    });

    const startYear = start.getFullYear();
    const endYear = end.getFullYear();

    if (startMonth === endMonth && startYear === endYear) {
        return `${startDay} – ${endDay} ${endMonth} ${endYear}`;
    }

    return `${startDay} ${startMonth} ${startYear} – ${endDay} ${endMonth} ${endYear}`;
}

function ChartTooltip({ active, payload, isStaff, contextEvents, contextEventError }) {
    if (!active || !payload || payload.length === 0) return null;

    const row = payload[0].payload;

    const matchingEvents = contextEvents.filter(
        (event) =>
            event.start_date <= row.date &&
            event.end_date >= row.date
    );

    const formattedDate = new Date(
        `${row.date}T12:00:00`
    ).toLocaleDateString("en-ZA", {
        day: "numeric",
        month: "long",
        year: "numeric",
    });

    return (
        <div className="chart-tooltip">
            <strong>{formattedDate}</strong>

            <div className="tooltip-row">
                <span>
                    <i className="legend-orders"></i>
                    Transactions
                </span>
                <b>{row.orders}</b>
            </div>

            <div className="tooltip-row">
                <span>
                    <i className="legend-customers"></i>
                    Customers
                </span>
                <b>{row.customers}</b>
            </div>

            {!isStaff && (
                <div className="tooltip-row">
                    <span>
                        <i className="legend-revenue"></i>
                        Revenue
                    </span>
                    <b>{formatRand(row.revenue)}</b>
                </div>
            )}

            <div className="tooltip-events">
                <strong>Contextual events</strong>

                {contextEventError ? (
                    <p>Events unavailable.</p>
                ) : matchingEvents.length > 0 ? (
                    <ul>
                        {matchingEvents.map((event) => (
                            <li key={event.event_id}>
                                {event.name}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p>No recorded events for this date.</p>
                )}
            </div>
        </div>
    );
}

function DemandForecast({
    onLogout,
    onBack,
    onDashboard,
    onFairComparison,
    onContextEvents,
    onOpenWeeklyEvidence,
}) {
    const [profileOpen, setProfileOpen] = useState(false);

    const [selectedComparisonDate, setSelectedComparisonDate] = useState("");
    const [comparisonMetric, setComparisonMetric] = useState("revenue");
    const defaultComparisonDateRequest = useRef(null);
    const [historicalComparison, setHistoricalComparison] = useState(null);
    const [comparisonLoading, setComparisonLoading] = useState(false);
    const [comparisonError, setComparisonError] = useState("");

    const [comparisonSort, setComparisonSort] = useState("newest");

    const [notificationsOpen, setNotificationsOpen] = useState(false);
    const [notifications, setNotifications] = useState([]);
    const [notificationsLoading, setNotificationsLoading] = useState(false);
    const [notificationsError, setNotificationsError] = useState("");
    const [expandedNotifications, setExpandedNotifications] = useState([]);


    const [showNotificationHistory, setShowNotificationHistory] = useState(false);
    const [historyNotifications, setHistoryNotifications] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyError, setHistoryError] = useState("");
    const [historyFilter, setHistoryFilter] = useState("all");

    const profileRef = useRef(null);

    const [vendors, setVendors] = useState([]);
    const [vendorId, setVendorId] = useState("21");

    const [businessSearch, setBusinessSearch] = useState("");
    const [debouncedBusinessSearch, setDebouncedBusinessSearch] = useState("");
    const [businessDropdownOpen, setBusinessDropdownOpen] = useState(false);

    const [forecastData, setForecastData] = useState([]);
    const [forecastSummary, setForecastSummary] = useState({
        expectedOrders: 0,
        expectedCustomers: 0,
        expectedRevenue: 0,
    });

    const [forecastPeriod, setForecastPeriod] = useState("");

    const [contextEvents, setContextEvents] = useState([]);
    const [contextEventError, setContextEventError] = useState("");
    const [forecastDates, setForecastDates] = useState({ start: "", end: "" });
    const [loadingVendors, setLoadingVendors] = useState(true);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [printing, setPrinting] = useState(false);

    const storedUser = getStoredUser();
    const currentUser = {
        name: storedUser?.full_name || storedUser?.email || "",
        role: storedUser?.role || "",
    };
    const isStaff = currentUser.role === "Staff"; // Staff never see revenue

    useEffect(() => {
        setComparisonMetric(isStaff ? "transactions" : "revenue");
    }, [isStaff]);

    const selectedVendorName =
        vendors.find((v) => String(v.vendor_id) === String(vendorId))?.name ||
        "";

    const filteredVendors = vendors.filter((vendor) =>
        (vendor.name || "")
            .toLowerCase()
            .includes(debouncedBusinessSearch.toLowerCase())
    );

    useEffect(() => {
        function handleClickOutside(event) {
            if (
                profileRef.current &&
                !profileRef.current.contains(event.target)
            ) {
                setProfileOpen(false);
            }
        }

        document.addEventListener(
            "mousedown",
            handleClickOutside
        );

        return () => {
            document.removeEventListener(
                "mousedown",
                handleClickOutside
            );
        };
    }, []);

    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedBusinessSearch(businessSearch);
        }, 300);

        return () => clearTimeout(timer);
    }, [businessSearch]);

    useEffect(() => {
        async function loadVendors() {
            try {
                setLoadingVendors(true);

                const response = await apiFetch("/vendors");


                if (!response.ok) {
                    throw new Error(
                        "Failed to load businesses."
                    );
                }

                const data = await response.json();

                setVendors(data);
                if (
                    data.length > 0 &&
                    !data.some((v) => String(v.vendor_id) === vendorId)
                ) {
                    setVendorId(String(data[0].vendor_id));
                }
            } catch (err) {
                setError(err.message);
            } finally {
                setLoadingVendors(false);
            }
        }

        loadVendors();
    }, []);

    useEffect(() => {
        const controller = new AbortController();

        async function loadContextEvents() {
            setContextEventError("");

            try {
                const response = await apiFetch("/context-events", {
                    signal: controller.signal,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error("Could not load contextual events.");
                }

                setContextEvents(
                    Array.isArray(data.events) ? data.events : []
                );
            } catch (err) {
                if (err.name !== "AbortError") {
                    setContextEventError(
                        "Contextual events could not be loaded."
                    );
                }
            }
        }

        loadContextEvents();

        return () => {
            controller.abort();
        };
    }, []);

    useEffect(() => {
        async function loadForecast() {
            if (!vendorId) return;

            if (defaultComparisonDateRequest.current === selectedComparisonDate) {
                defaultComparisonDateRequest.current = null;
                return;
            }

            try {
                setLoading(true);
                setError("");

                const query = selectedComparisonDate
                    ? `?selected_date=${selectedComparisonDate}`
                    : "";

                const response = await apiFetch(
                    `/vendors/${vendorId}/demand-forecast${query}`
                );


                if (!response.ok) {
                    throw new Error(
                        "Failed to load demand forecast."
                    );
                }

                const data = await response.json();

                setHistoricalComparison(data.historical_comparison ?? null);
                setComparisonError("");

                if (
                    !selectedComparisonDate &&
                    data.historical_comparison?.selected_week_start
                ) {
                    defaultComparisonDateRequest.current =
                        data.historical_comparison.selected_week_start;
                    setSelectedComparisonDate(
                        data.historical_comparison.selected_week_start
                    );
                }

                if (data.error) {
                    if (
                        data.error ===
                        "No transaction history for this vendor"
                    ) {
                        setForecastData([]);
                        setHistoricalComparison(null);
                        setComparisonError(
                            "No transaction history available for comparison."
                        );

                        setForecastSummary({
                            expectedOrders: 0,
                            expectedCustomers: 0,
                            expectedRevenue: 0,
                        });

                        setError("NO_DATA");

                        return;
                    }

                    throw new Error(data.error);
                }

                const formattedData = data.points.map(
                    (point) => ({
                        date: point.date,
                        day: point.day_of_week.substring(0, 3),
                        orders: point.expected_orders,
                        customers: point.expected_customers,
                        revenue: point.expected_revenue,
                    })
                );
                const firstDate = new Date(
                    `${data.points[0].date}T12:00:00`
                );

                const lastDate = new Date(
                    `${data.points[data.points.length - 1].date}T12:00:00`
                );

                const formatDate = (date) =>
                    date.toLocaleDateString("en-ZA", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                    });

                setForecastPeriod(
                    `${formatDate(firstDate)} - ${formatDate(
                        lastDate
                    )}`
                );

                setForecastDates({
                    start: data.points[0].date,
                    end: data.points[data.points.length - 1].date,
                });

                setForecastData(formattedData);

                const expectedOrders =
                    formattedData.reduce(
                        (total, item) =>
                            total + item.orders,
                        0
                    );

                const expectedCustomers =
                    formattedData.reduce(
                        (total, item) =>
                            total + item.customers,
                        0
                    );

                const expectedRevenue =
                    formattedData.reduce(
                        (total, item) =>
                            total + item.revenue,
                        0
                    );

                setForecastSummary({
                    expectedOrders,
                    expectedCustomers,
                    expectedRevenue,
                });
            } catch (err) {
                console.error("Error loading forecast:", err);

                setHistoricalComparison(null);
                setComparisonError(err.message);

                setForecastData([]);

                setForecastSummary({
                    expectedOrders: 0,
                    expectedCustomers: 0,
                    expectedRevenue: 0,
                });
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }

        loadForecast();
    }, [vendorId, selectedComparisonDate]);


    async function loadNotifications() {
        if (!vendorId) return;

        try {
            setNotificationsLoading(true);
            setNotificationsError("");

            const response = await apiFetch(
                `/notifications?vendor_id=${vendorId}`
            );

            if (!response.ok) {
                throw new Error("Could not load notifications.");
            }

            const data = await response.json();
            setNotifications(Array.isArray(data) ? data : []);
        } catch (err) {
            setNotificationsError(err.message);
        } finally {
            setNotificationsLoading(false);
        }
    }

    useEffect(() => {
        loadNotifications();
    }, [vendorId]);

    async function loadNotificationHistory() {
        if (!vendorId) return;

        try {
            setHistoryLoading(true);
            setHistoryError("");

            const response = await apiFetch(
                `/notifications?vendor_id=${vendorId}&include_cleared=true`
            );

            if (!response.ok) {
                throw new Error("Could not load notification history.");
            }

            const data = await response.json();
            setHistoryNotifications(Array.isArray(data) ? data : []);
        } catch (err) {
            setHistoryError(err.message);
        } finally {
            setHistoryLoading(false);
        }
    }

    async function openNotificationHistory() {
        setNotificationsOpen(false);
        setHistoryFilter("all");
        setShowNotificationHistory(true);

        await loadNotificationHistory();
    }

    async function updateNotification(notificationId, action) {
        try {
            const response = await apiFetch(
                `/notifications/${notificationId}/${action}`,
                { method: "PATCH" }
            );

            if (!response.ok) {
                throw new Error("Could not update notification.");
            }

            await loadNotifications();
        } catch (err) {
            setNotificationsError(err.message);
        }
    }

    async function openNotifications() {
        const willOpen = !notificationsOpen;
        setNotificationsOpen(willOpen);

        if (willOpen) {
            await loadNotifications();
        }
    }

    function handleLogout() {
        setProfileOpen(false);
        onLogout();
    }

    return (
        <div className="app-layout">

            <WorkspaceSidebar
                activeView="demand"
                onNavigate={(view) => ({
                    dashboard: onDashboard,
                    rush: onBack,
                    fair: onFairComparison,
                    context: onContextEvents,
                }[view]?.())}
            />

            <main className="main-content">

                <header className="topbar">

                    <div className="breadcrumb">
                        Workspace /{" "}
                        <strong>Demand Forecast</strong>
                    </div>

                    <div className="topbar-right">


                        <div className="notification-container">
                            <button
                                type="button"
                                className="notification-button"
                                onClick={openNotifications}
                                aria-label="Notifications"
                                title="Notifications"
                                aria-expanded={notificationsOpen}
                            >
                                <Bell size={18} />

                                {notifications.some((item) => !item.is_read && !item.is_cleared) && (
                                    <span className="notification-dot" />
                                )}
                            </button>

                            {notificationsOpen && (
                                <div className="notification-panel">
                                    <div className="notification-panel-header">
                                        <h3>Notifications</h3>

                                        <button
                                            type="button"
                                            onClick={() => setNotificationsOpen(false)}
                                            aria-label="Close notifications"
                                        >
                                            <X size={18} />
                                        </button>
                                    </div>

                                    {notificationsLoading && (
                                        <p>Loading notifications...</p>
                                    )}

                                    {notificationsError && (
                                        <p className="notification-error">
                                            {notificationsError}
                                        </p>
                                    )}

                                    {!notificationsLoading &&
                                        !notificationsError &&
                                        notifications.length === 0 && (
                                            <p>No notifications yet.</p>
                                        )}

                                    {!notificationsLoading &&
                                        !notificationsError &&
                                        notifications.map((item) => (

                                            <div
                                                key={item.notification_id}
                                                className={`notification-history-card ${item.is_read ? "read" : "unread"} ${item.is_cleared ? "cleared" : ""}`}
                                            >

                                                <div className="notification-detail-heading">
                                                    <div className="notification-heading-text">
                                                        <h3>
                                                            {item.direction === "increased"
                                                                ? "Unusual increase in transactions"
                                                                : item.direction === "decreased"
                                                                    ? "Unusual decrease in transactions"
                                                                    : "Transaction alert"}
                                                        </h3>

                                                        <p className="notification-type">
                                                            Historical transaction alert
                                                        </p>
                                                    </div>

                                                    <div className="notification-heading-controls">
                                                        <div className="history-statuses">
                                                            {item.is_pinned && (
                                                                <span className="history-status pinned-status">
                                                                    Pinned
                                                                </span>
                                                            )}

                                                            <span
                                                                className={`history-status ${item.is_read ? "" : "unread-status"
                                                                    }`}
                                                            >
                                                                {item.is_read ? "Read" : "Unread"}
                                                            </span>
                                                        </div>

                                                        <button
                                                            type="button"
                                                            className="notification-expand-button"
                                                            onClick={() => {
                                                                setExpandedNotifications((current) =>
                                                                    current.includes(item.notification_id)
                                                                        ? current.filter(
                                                                            (id) => id !== item.notification_id
                                                                        )
                                                                        : [...current, item.notification_id]
                                                                );
                                                            }}
                                                            aria-label={
                                                                expandedNotifications.includes(item.notification_id)
                                                                    ? "Hide details"
                                                                    : "View details"
                                                            }
                                                            aria-expanded={expandedNotifications.includes(
                                                                item.notification_id
                                                            )}
                                                        >
                                                            <ChevronDown
                                                                size={18}
                                                                style={{
                                                                    transform: expandedNotifications.includes(
                                                                        item.notification_id
                                                                    )
                                                                        ? "rotate(180deg)"
                                                                        : "rotate(0deg)",
                                                                    transition: "transform 0.2s ease",
                                                                }}
                                                            />
                                                        </button>
                                                    </div>
                                                </div>

                                                <p className="notification-analysis-date">
                                                    Date analysed:{" "}
                                                    {item.transaction_date
                                                        ? new Date(`${item.transaction_date}T12:00:00`).toLocaleDateString("en-ZA", {
                                                            weekday: "long",
                                                            day: "numeric",
                                                            month: "long",
                                                            year: "numeric",
                                                        })
                                                        : "Date unavailable"}
                                                </p>

                                                <div className="notification-percentage">
                                                    {item.percentage_change != null
                                                        ? `${item.direction === "decreased" ? "−" : "+"}${Math.round(item.percentage_change)}%`
                                                        : "—"}
                                                </div>

                                                <p className="notification-summary">
                                                    Transaction volume was{" "}
                                                    {item.direction === "decreased" ? "lower" : "higher"}{" "}
                                                    than the usual level for{" "}
                                                    {item.transaction_date
                                                        ? new Date(`${item.transaction_date}T12:00:00`).toLocaleDateString("en-ZA", {
                                                            weekday: "long",
                                                        })
                                                        : "this weekday"}.
                                                </p>

                                                {expandedNotifications.includes(item.notification_id) && (
                                                    <>

                                                        <div className="notification-stats">
                                                            <div className="notification-stat">
                                                                <span>Actual count</span>
                                                                <strong>{item.actual_count ?? "—"}</strong>
                                                            </div>

                                                            <div className="notification-stat">
                                                                <span>Usual count</span>
                                                                <strong>
                                                                    {item.baseline_count != null
                                                                        ? item.baseline_count.toFixed(1)
                                                                        : "—"}
                                                                </strong>
                                                            </div>
                                                        </div>

                                                        <p className="notification-baseline">
                                                            Baseline: average across the four previous occurrences of the same weekday.
                                                        </p>

                                                        <div className="notification-context-events">
                                                            <strong>Contextual events</strong>

                                                            {Array.isArray(item.contextual_events) &&
                                                                item.contextual_events.length > 0 ? (
                                                                <>
                                                                    <p>
                                                                        The following events coincided with this transaction change:
                                                                    </p>
                                                                    <ul>
                                                                        {item.contextual_events.map((event) => (
                                                                            <li key={event.event_id}>{event.name}</li>
                                                                        ))}
                                                                    </ul>
                                                                </>
                                                            ) : (
                                                                <p>No contextual events recorded for this date.</p>
                                                            )}
                                                        </div>

                                                        <p className="notification-created-date">
                                                            Notification created:{" "}
                                                            {item.created_at
                                                                ? new Date(item.created_at).toLocaleString("en-ZA", {
                                                                    day: "numeric",
                                                                    month: "long",
                                                                    year: "numeric",
                                                                    hour: "2-digit",
                                                                    minute: "2-digit",
                                                                })
                                                                : "Unavailable"}
                                                        </p>

                                                        <div className="history-card-actions">
                                                            {!item.is_read && (
                                                                <button
                                                                    type="button"
                                                                    className="history-action-button"
                                                                    onClick={() => updateNotification(item.notification_id, "read")}
                                                                >
                                                                    Mark read
                                                                </button>
                                                            )}

                                                            <button
                                                                type="button"
                                                                className="history-action-button"
                                                                onClick={() => updateNotification(item.notification_id, "pin")}
                                                            >
                                                                {item.is_pinned ? "Unpin" : "Pin"}
                                                            </button>

                                                            <button
                                                                type="button"
                                                                className="history-action-button clear-action"
                                                                onClick={() => updateNotification(item.notification_id, "clear")}
                                                            >
                                                                Clear
                                                            </button>
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        ))}

                                    <button
                                        type="button"
                                        className="view-all-notifications"
                                        onClick={openNotificationHistory}
                                    >
                                        View all notifications
                                    </button>

                                </div>
                            )}
                        </div>

                        <div
                            className="profile-container"
                            ref={profileRef}
                        >
                            <button
                                className="user-profile"
                                onClick={() =>
                                    setProfileOpen(
                                        (open) => !open
                                    )
                                }
                                aria-label="Open user menu"
                            >
                                <div className="user-avatar">
                                    {currentUser.name.charAt(
                                        0
                                    )}
                                </div>

                                <div className="user-details">
                                    <strong>
                                        {currentUser.name}
                                    </strong>

                                    <span>
                                        {currentUser.role}
                                    </span>
                                </div>

                                <ChevronDown
                                    size={14}
                                    className="profile-chevron"
                                />
                            </button>

                            {profileOpen && (
                                <div className="profile-dropdown">
                                    
                                    <button
                                        className="logout-option"
                                        onClick={handleLogout}
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

                    {showNotificationHistory ? (
                        <section className="notification-history-page">

                            <button
                                type="button"
                                className="back-to-forecast"
                                onClick={() => setShowNotificationHistory(false)}
                            >

                                <ArrowLeft size={22} />
                                Back
                            </button>

                            <h1>Notification History</h1>

                            <p>
                                View previous notifications for the selected business, including notifications that you have cleared.
                            </p>

                            <label htmlFor="notification-history-filter">
                                Filter notifications
                            </label>

                            <select
                                id="notification-history-filter"
                                value={historyFilter}
                                onChange={(event) => setHistoryFilter(event.target.value)}
                            >
                                <option value="all">All notifications</option>
                                <option value="unread">Unread</option>
                                <option value="pinned">Pinned</option>
                                <option value="cleared">Cleared</option>
                            </select>

                            {historyLoading && (
                                <p>Loading notification history...</p>
                            )}

                            {historyError && (
                                <p className="notification-error">{historyError}</p>
                            )}

                            {!historyLoading && !historyError && (
                                <>
                                    {historyNotifications
                                        .filter((item) => {
                                            if (historyFilter === "unread") {
                                                return !item.is_read && !item.is_cleared;
                                            }

                                            if (historyFilter === "pinned") {
                                                return item.is_pinned;
                                            }

                                            if (historyFilter === "cleared") {
                                                return item.is_cleared;
                                            }

                                            return true;
                                        })

                                        .map((item) => (
                                            <div
                                                key={item.notification_id}
                                                className={`notification-history-card ${item.is_read ? "read" : "unread"} ${item.is_cleared ? "cleared" : ""}`}
                                            >
                                                <div className="history-card-top">
                                                    <div className="history-card-heading">
                                                        <span className={`history-type-icon ${item.trigger_type === "transaction_increase" ? "increase" : "decrease"}`}>
                                                            {item.trigger_type === "transaction_increase" ? (
                                                                <ArrowUp size={16} />
                                                            ) : (
                                                                <ArrowDown size={16} />
                                                            )}
                                                        </span>

                                                        <div>
                                                            <h3>
                                                                {item.trigger_type === "transaction_increase"
                                                                    ? "Transaction increase"
                                                                    : item.trigger_type === "transaction_decrease"
                                                                        ? "Transaction decrease"
                                                                        : "Notification"}
                                                            </h3>


                                                            <small>
                                                                Transaction date:{" "}
                                                                {item.transaction_date
                                                                    ? new Date(
                                                                        `${item.transaction_date}T12:00:00`
                                                                    ).toLocaleDateString("en-ZA", {
                                                                        day: "numeric",
                                                                        month: "long",
                                                                        year: "numeric",
                                                                    })
                                                                    : "Date unavailable"}
                                                            </small>

                                                            <small className="notification-created-date">
                                                                Notification created:{" "}
                                                                {item.created_at
                                                                    ? new Date(item.created_at).toLocaleString("en-ZA", {
                                                                        day: "numeric",
                                                                        month: "short",
                                                                        year: "numeric",
                                                                        hour: "2-digit",
                                                                        minute: "2-digit",
                                                                    })
                                                                    : ""}
                                                            </small>
                                                        </div>
                                                    </div>

                                                    <div className="history-statuses">
                                                        {item.is_pinned && (
                                                            <span className="history-status pinned-status">
                                                                Pinned
                                                            </span>
                                                        )}

                                                        {item.is_cleared && (
                                                            <span className="history-status cleared-status">
                                                                Cleared
                                                            </span>
                                                        )}

                                                        {!item.is_read && !item.is_cleared && (
                                                            <span className="history-status unread-status">
                                                                Unread
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                <p className="history-card-message">
                                                    {(item.message || "").replace(/^\[[^\]]+\]\s*/, "")}
                                                </p>

                                                <div className="notification-context-events">
                                                    <strong>Contextual events</strong>

                                                    {Array.isArray(item.contextual_events) &&
                                                        item.contextual_events.length > 0 ? (
                                                        <ul>
                                                            {item.contextual_events.map((event) => (
                                                                <li key={event.event_id}>
                                                                    {event.name}
                                                                    <small>
                                                                        {" "}({event.start_date} to {event.end_date})
                                                                    </small>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    ) : (
                                                        <p>No contextual events recorded for this date.</p>
                                                    )}
                                                </div>

                                                <div className="history-card-actions">
                                                    {!item.is_read && (
                                                        <button
                                                            type="button"
                                                            className="history-action-button"
                                                            onClick={async () => {
                                                                await updateNotification(
                                                                    item.notification_id,
                                                                    "read"
                                                                );
                                                                await loadNotificationHistory();
                                                            }}
                                                        >
                                                            Mark read
                                                        </button>
                                                    )}

                                                    <button
                                                        type="button"
                                                        className="history-action-button"
                                                        onClick={async () => {
                                                            await updateNotification(
                                                                item.notification_id,
                                                                "pin"
                                                            );
                                                            await loadNotificationHistory();
                                                        }}
                                                    >
                                                        {item.is_pinned ? "Unpin" : "Pin"}
                                                    </button>

                                                    {!item.is_cleared && (
                                                        <button
                                                            type="button"
                                                            className="history-action-button clear-action"
                                                            onClick={async () => {
                                                                await updateNotification(
                                                                    item.notification_id,
                                                                    "clear"
                                                                );
                                                                await loadNotificationHistory();
                                                            }}
                                                        >
                                                            Clear
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        ))}

                                    {historyNotifications.filter((item) => {
                                        if (historyFilter === "unread") {
                                            return !item.is_read && !item.is_cleared;
                                        }

                                        if (historyFilter === "pinned") {
                                            return item.is_pinned;
                                        }

                                        if (historyFilter === "cleared") {
                                            return item.is_cleared;
                                        }

                                        return true;
                                    }).length === 0 && (
                                            <p>No notifications in this category.</p>
                                        )}
                                </>
                            )}
                        </section>
                    ) : (
                        <>
                            <>
                                <div className="demand-page-header report-heading">
                                    <div className="page-heading">
                                        <h1>Demand Forecast</h1>

                                        <p>
                                            View expected demand based on historical transaction patterns.
                                        </p>
                                    </div>

                                    <div className="business-selector-row">
                                        <div className="business-selector-field">
                                            <label className="business-selector-label">
                                                Business
                                            </label>

                                            <div className="business-search-container">
                                                <input
                                                    type="text"
                                                    className="business-selector"
                                                    placeholder="Search businesses..."
                                                    value={
                                                        businessDropdownOpen
                                                            ? businessSearch
                                                            : selectedVendorName
                                                    }
                                                    onFocus={() => {
                                                        setBusinessSearch("");
                                                        setDebouncedBusinessSearch("");
                                                        setBusinessDropdownOpen(true);
                                                    }}
                                                    onChange={(event) => {
                                                        setBusinessSearch(event.target.value);
                                                        setBusinessDropdownOpen(true);
                                                    }}
                                                    disabled={loadingVendors}
                                                    aria-label="Search businesses"
                                                    aria-expanded={businessDropdownOpen}
                                                    aria-controls="business-search-results"
                                                    autoComplete="off"
                                                />

                                                {businessDropdownOpen && (
                                                    <div
                                                        id="business-search-results"
                                                        className="business-search-results"
                                                        role="listbox"
                                                    >
                                                        {filteredVendors.length > 0 ? (
                                                            filteredVendors.map((vendor) => (
                                                                <button
                                                                    key={vendor.vendor_id}
                                                                    type="button"
                                                                    className="business-search-option"
                                                                    role="option"
                                                                    aria-selected={
                                                                        String(vendor.vendor_id) ===
                                                                        String(vendorId)
                                                                    }
                                                                    onMouseDown={(event) =>
                                                                        event.preventDefault()
                                                                    }

                                                                    onClick={() => {
                                                                        setVendorId(String(vendor.vendor_id));
                                                                        setSelectedComparisonDate("");
                                                                        setHistoricalComparison(null);
                                                                        setComparisonError("");
                                                                        setBusinessSearch("");
                                                                        setDebouncedBusinessSearch("");
                                                                        setBusinessDropdownOpen(false);
                                                                    }}

                                                                >
                                                                    {vendor.name}
                                                                </button>
                                                            ))
                                                        ) : (
                                                            <div className="business-search-empty">
                                                                No businesses found
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {forecastData.length > 0 && (
                                        <ReportButton
                                            title="Demand Forecast"
                                            subtitle={`${selectedVendorName} · ${forecastPeriod}`}
                                            reportType="demand_forecast"
                                            vendorId={vendorId}
                                            periodStart={forecastDates.start}
                                            periodEnd={forecastDates.end}
                                            onPrintStart={() => setPrinting(true)}
                                            onPrintEnd={() => setPrinting(false)}
                                        />
                                    )}
                                </div>

                                {loading && (
                                    <p>
                                        Loading demand forecast...
                                    </p>
                                )}

                                {error === "NO_DATA" && (
                                    <p>
                                        No forecast is available for this business because there is no transaction history available.
                                    </p>
                                )}

                                {error && error !== "NO_DATA" && (
                                    <p style={{ color: "#b34c57" }}>
                                        Unable to load demand forecast:{" "}
                                        {error}
                                    </p>
                                )}

                                {!loading &&
                                    !error &&
                                    forecastData.length > 0 && (
                                        <>
                                            <section className="summary-grid">

                                                <div className="summary-card">
                                                    <span>
                                                        EXPECTED TRANSACTIONS
                                                    </span>

                                                    <strong>
                                                        {forecastSummary.expectedOrders}
                                                    </strong>

                                                    <small>
                                                        {forecastPeriod}
                                                    </small>
                                                </div>

                                                <div className="summary-card">
                                                    <span>
                                                        EXPECTED CUSTOMERS
                                                    </span>

                                                    <strong>
                                                        {forecastSummary.expectedCustomers}
                                                    </strong>

                                                    <small>
                                                        {forecastPeriod}
                                                    </small>
                                                </div>

                                                {!isStaff && (
                                                    <div className="summary-card">
                                                        <span>EXPECTED REVENUE</span>
                                                        <strong>
                                                            {formatRand(forecastSummary.expectedRevenue)}
                                                        </strong>
                                                        <small>{forecastPeriod}</small>
                                                    </div>
                                                )}

                                            </section>

                                            <section className="forecast-card">

                                                <div className="forecast-card-header">

                                                    <div>
                                                        <h2>
                                                            Weekly Demand Forecast
                                                        </h2>

                                                        <p>
                                                            Expected transactions, customers and revenue for the forecast period.
                                                        </p>
                                                    </div>

                                                    <div className="forecast-legend">

                                                        <span>
                                                            <i className="legend-orders"></i>
                                                            Transactions
                                                        </span>

                                                        <span>
                                                            <i className="legend-customers"></i>
                                                            Customers
                                                        </span>

                                                        {!isStaff && (
                                                            <span>
                                                                <i className="legend-revenue"></i>
                                                                Revenue
                                                            </span>
                                                        )}

                                                    </div>

                                                </div>

                                                <div className="forecast-chart">

                                                    <ResponsiveContainer
                                                        width={printing ? 640 : "100%"}
                                                        height="100%"
                                                    >
                                                        <LineChart
                                                            data={
                                                                forecastData
                                                            }
                                                            margin={{
                                                                top: 10,
                                                                right: 10,
                                                                left: 0,
                                                                bottom: 0,
                                                            }}
                                                        >

                                                            <CartesianGrid
                                                                stroke="#e0e0e0"
                                                                strokeWidth={1}
                                                                horizontal={true}
                                                                vertical={true}
                                                            />

                                                            <XAxis
                                                                dataKey="day"
                                                                tick={{
                                                                    fontSize: 11,
                                                                    fill: "#7c8987",
                                                                }}
                                                                tickLine={false}
                                                                axisLine={{
                                                                    stroke:
                                                                        "#dfe7e4",
                                                                }}
                                                                interval={0}
                                                            />

                                                            <YAxis
                                                                yAxisId="left"
                                                                tick={{
                                                                    fontSize: 11,
                                                                    fill: "#7c8987",
                                                                }}
                                                                tickLine={false}
                                                                axisLine={false}
                                                                width={40}
                                                                tickCount={6}
                                                            />

                                                            <YAxis
                                                                yAxisId="right"
                                                                orientation="right"
                                                                tick={{
                                                                    fontSize: 11,
                                                                    fill: "#7c8987",
                                                                }}
                                                                tickLine={false}
                                                                axisLine={false}
                                                                width={48}
                                                                tickFormatter={(v) => `R${(v / 1000).toFixed(2)}k`}
                                                            />

                                                            <Tooltip
                                                                content={
                                                                    <ChartTooltip
                                                                        isStaff={isStaff}
                                                                        contextEvents={contextEvents}
                                                                        contextEventError={contextEventError}
                                                                    />
                                                                }
                                                                cursor={{
                                                                    stroke: "#c9d6d2",
                                                                }}
                                                            />

                                                            <Line
                                                                yAxisId="left"
                                                                type="monotone"
                                                                dataKey="orders"
                                                                stroke="#b34c57"
                                                                strokeWidth={3}
                                                                dot={{ r: 3 }}
                                                                isAnimationActive={!printing}
                                                                activeDot={{
                                                                    r: 6,
                                                                }}
                                                            />

                                                            <Line
                                                                yAxisId="left"
                                                                type="monotone"
                                                                dataKey="customers"
                                                                stroke="#2e8f87"
                                                                strokeWidth={3}
                                                                dot={{ r: 3 }}
                                                                isAnimationActive={!printing}
                                                                activeDot={{
                                                                    r: 6,
                                                                }}
                                                            />

                                                            {!isStaff && (
                                                                <Line
                                                                    yAxisId="right"
                                                                    type="monotone"
                                                                    dataKey="revenue"
                                                                    stroke="#7faaa4"
                                                                    strokeWidth={3}
                                                                    strokeDasharray="7 5"
                                                                    dot={{ r: 3 }}
                                                                    isAnimationActive={!printing}
                                                                    activeDot={{ r: 6 }}
                                                                />
                                                            )}

                                                        </LineChart>
                                                    </ResponsiveContainer>

                                                </div>

                                                <div className="forecast-details">

                                                    <h2 className="daily-figures-heading">
                                                        View daily figures
                                                    </h2>

                                                    <div className="table-scroll">

                                                        <table className="forecast-table">

                                                            <thead>
                                                                <tr>
                                                                    <th>Day</th>
                                                                    <th>Transactions</th>
                                                                    <th>Customers</th>
                                                                    {!isStaff && <th>Revenue</th>}
                                                                    <th>Event</th>
                                                                </tr>
                                                            </thead>

                                                            <tbody>
                                                                {forecastData.map((item) => {
                                                                    const matchingEvents = contextEvents.filter(
                                                                        (event) =>
                                                                            event.start_date <= item.date &&
                                                                            event.end_date >= item.date
                                                                    );

                                                                    return (
                                                                        <tr key={item.date}>
                                                                            <td>{item.day}</td>
                                                                            <td>{item.orders}</td>
                                                                            <td>{item.customers}</td>

                                                                            {!isStaff && (
                                                                                <td>{formatRand(item.revenue)}</td>
                                                                            )}

                                                                            <td>
                                                                                {contextEventError
                                                                                    ? "Unavailable"
                                                                                    : matchingEvents.length > 0
                                                                                        ? matchingEvents
                                                                                            .map((event) => event.name)
                                                                                            .join(", ")
                                                                                        : "-"}
                                                                            </td>
                                                                        </tr>
                                                                    );
                                                                })}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                </div>

                                                <div className="forecast-note">
                                                    Forecasts are estimates based on historical transaction patterns and may be affected by contextual factors such as holidays, exams and events.
                                                </div>
                                            </section>


                                            <section className="historical-comparison-card">
                                                <div className="historical-comparison-header">
                                                    <div>
                                                        <h2>Historical Activity Comparison</h2>
                                                        <p>Compare recorded transaction activity across weeks.</p>
                                                    </div>

                                                    <button
                                                        type="button"
                                                        className="view-evidence-button"
                                                        onClick={() =>
                                                            onOpenWeeklyEvidence?.({
                                                                vendorId,
                                                                vendorName: selectedVendorName,
                                                                selectedDate:
                                                                    historicalComparison?.selected_week_start ||
                                                                    selectedComparisonDate,
                                                                metric: comparisonMetric,
                                                            })
                                                        }
                                                        disabled={!historicalComparison}
                                                    >
                                                        View
                                                    </button>
                                                </div>


                                                <div className="comparison-controls">
                                                    <div className="comparison-week-selector">
                                                        <label htmlFor="comparison-week-date">
                                                            Choose a date in the week
                                                        </label>

                                                        <input
                                                            id="comparison-week-date"
                                                            type="date"
                                                            value={selectedComparisonDate}
                                                            onChange={(event) =>
                                                                setSelectedComparisonDate(event.target.value)
                                                            }
                                                        />

                                                        <p>
                                                            The selected date determines the Monday-Sunday week. The preceding week is compared automatically.
                                                        </p>
                                                    </div>

                                                    <div className="comparison-metric-selector">
                                                        <label htmlFor="comparison-metric">
                                                            Compare by
                                                        </label>

                                                        <select
                                                            id="comparison-metric"
                                                            value={comparisonMetric}
                                                            onChange={(event) =>
                                                                setComparisonMetric(event.target.value)
                                                            }
                                                        >
                                                            {!isStaff && (
                                                                <option value="revenue">Revenue</option>
                                                            )}

                                                            <option value="transactions">Transactions</option>
                                                        </select>
                                                    </div>
                                                </div>


                                                {comparisonLoading && (
                                                    <p>Loading historical activity...</p>
                                                )}

                                                {comparisonError && (
                                                    <p className="comparison-error">{comparisonError}</p>
                                                )}

                                                {!comparisonLoading &&
                                                    !comparisonError &&
                                                    historicalComparison && (
                                                        <>
                                                            <div className="comparison-period-cards">
                                                                <div className="comparison-period-item">
                                                                    <span>Selected week</span>
                                                                    <strong>
                                                                        {formatComparisonPeriod(
                                                                            historicalComparison.selected_week_start,
                                                                            historicalComparison.selected_week_end
                                                                        )}
                                                                    </strong>
                                                                </div>

                                                                <div className="comparison-period-item">
                                                                    <span>Previous week</span>
                                                                    <strong>
                                                                        {formatComparisonPeriod(
                                                                            historicalComparison.previous_week_start,
                                                                            historicalComparison.previous_week_end
                                                                        )}
                                                                    </strong>
                                                                </div>
                                                            </div>

                                                            <div className="table-scroll">
                                                                <table className="historical-comparison-table">


                                                                    <thead>
                                                                        <tr>
                                                                            <th>Day</th>
                                                                            <th>Date</th>

                                                                            <th>
                                                                                {comparisonMetric === "revenue"
                                                                                    ? "This week's Revenue (R)"
                                                                                    : "This week's Transactions"}
                                                                            </th>

                                                                            <th>
                                                                                {comparisonMetric === "revenue"
                                                                                    ? "Previous week's Revenue (R)"
                                                                                    : "Previous week's Transactions"}
                                                                            </th>

                                                                            <th>% Change</th>
                                                                            <th>Activity category</th>
                                                                        </tr>
                                                                    </thead>


                                                                    <tbody>
                                                                        {historicalComparison.days.map((day) => {

                                                                            const isRevenue = comparisonMetric === "revenue";

                                                                            const currentValue = isRevenue
                                                                                ? day.this_week_revenue
                                                                                : day.this_week_orders;

                                                                            const previousValue = isRevenue
                                                                                ? day.previous_week_revenue
                                                                                : day.previous_week_orders;

                                                                            const change = isRevenue
                                                                                ? day.revenue_percentage_change
                                                                                : day.orders_percentage_change;

                                                                            const hasBothCounts =
                                                                                currentValue != null &&
                                                                                previousValue != null;

                                                                            const hasComparisonData =
                                                                                hasBothCounts && change != null;

                                                                            let category = "Usual";
                                                                            let categoryClass = "usual";

                                                                            if (!hasComparisonData) {
                                                                                category = "Insufficient data";
                                                                                categoryClass = "insufficient";
                                                                            } else if (change >= 10) {
                                                                                category = "High activity";
                                                                                categoryClass = "high";
                                                                            } else if (change > 0) {
                                                                                category = "Above average";
                                                                                categoryClass = "above";
                                                                            } else if (change < 0) {
                                                                                category = "Below average";
                                                                                categoryClass = "below";
                                                                            }

                                                                            const dateObject = new Date(`${day.date}T12:00:00`);

                                                                            const formattedDay = dateObject.toLocaleDateString("en-ZA", {
                                                                                weekday: "long",
                                                                            });

                                                                            const formattedDate = dateObject.toLocaleDateString("en-ZA", {
                                                                                day: "numeric",
                                                                                month: "short",
                                                                                year: "numeric",
                                                                            });


                                                                            return (

                                                                                <tr key={day.date}>
                                                                                    <td>{formattedDay}</td>
                                                                                    <td>{formattedDate}</td>


                                                                                    <td>
                                                                                        {currentValue == null
                                                                                            ? "N/A"
                                                                                            : isRevenue
                                                                                                ? Number(currentValue).toLocaleString("en-US", {
                                                                                                    minimumFractionDigits: 2,
                                                                                                    maximumFractionDigits: 2,
                                                                                                }).replace(/,/g, " ")
                                                                                                : Number(currentValue).toLocaleString("en-ZA")}
                                                                                    </td>

                                                                                    <td>
                                                                                        {previousValue == null
                                                                                            ? "N/A"
                                                                                            : isRevenue
                                                                                                ? Number(previousValue).toLocaleString("en-US", {
                                                                                                    minimumFractionDigits: 2,
                                                                                                    maximumFractionDigits: 2,
                                                                                                }).replace(/,/g, " ")
                                                                                                : Number(previousValue).toLocaleString("en-ZA")}
                                                                                    </td>

                                                                                    <td>
                                                                                        {!hasComparisonData ? (
                                                                                            <span className="comparison-change insufficient">
                                                                                                —
                                                                                            </span>
                                                                                        ) : (
                                                                                            <span className={`comparison-change ${categoryClass}`}>
                                                                                                {change > 0 && <ArrowUp size={14} />}
                                                                                                {change < 0 && <ArrowDown size={14} />}
                                                                                                {change > 0 ? "+" : ""}
                                                                                                {formatNumber(change)}%
                                                                                            </span>
                                                                                        )}
                                                                                    </td>
                                                                                    <td>
                                                                                        <span className={`activity-category ${categoryClass}`}>
                                                                                            {category}
                                                                                        </span>
                                                                                    </td>
                                                                                </tr>
                                                                            );
                                                                        })}
                                                                    </tbody>
                                                                </table>
                                                            </div>

                                                            <p className="historical-comparison-note">
                                                                Figures are based on recorded loyalty transactions and may not reflect total business activity.
                                                            </p>
                                                        </>
                                                    )}
                                            </section>
                                        </>
                                    )}
                            </>
                        </>
                    )}

                </div>

            </main>
        </div>
    );
}

export default DemandForecast;