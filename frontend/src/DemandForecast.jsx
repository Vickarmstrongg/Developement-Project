import { useEffect, useState } from "react";
import logo from "./assets/Logo.png";
import {
    Bell,
    Clock3,
    TrendingUp,
    Scale,
    FileText,
    LogOut,
    ChevronDown,
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

function formatRand(value) {
    return `R ${value.toLocaleString("en-ZA")}`;
}

function ChartTooltip({ active, payload }) {
    if (!active || !payload || payload.length === 0) return null;

    const row = payload[0].payload;

    return (
        <div className="chart-tooltip">
            <strong>{row.day}</strong>

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

            <div className="tooltip-row">
                <span>
                    <i className="legend-revenue"></i>
                    Revenue
                </span>
                <b>{formatRand(row.revenue)}</b>
            </div>
        </div>
    );
}

function DemandForecast({ onLogout, onBack }) {
    const [profileOpen, setProfileOpen] = useState(false);

    const [vendors, setVendors] = useState([]);
    const [vendorId, setVendorId] = useState("21");

    const [forecastData, setForecastData] = useState([]);
    const [forecastSummary, setForecastSummary] = useState({
        expectedOrders: 0,
        expectedCustomers: 0,
        expectedRevenue: 0,
    });

    const [forecastPeriod, setForecastPeriod] = useState("");

    const [loadingVendors, setLoadingVendors] = useState(true);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const currentUser = {
        name: "User Name",
        role: "Manager",
    };

    useEffect(() => {
        async function loadVendors() {
            try {
                setLoadingVendors(true);

                const response = await fetch(
                    "http://127.0.0.1:8000/vendors"
                );

                if (!response.ok) {
                    throw new Error("Failed to load businesses.");
                }

                const data = await response.json();

                setVendors(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoadingVendors(false);
            }
        }

        loadVendors();
    }, []);

    useEffect(() => {
        async function loadForecast() {
            if (!vendorId) return;

            try {
                setLoading(true);
                setError("");

                const response = await fetch(
                    `http://127.0.0.1:8000/vendors/${vendorId}/demand-forecast`
                );

                if (!response.ok) {
                    throw new Error("Failed to load demand forecast.");
                }

                const data = await response.json();

                if (data.error) {
                    if (
                        data.error ===
                        "No transaction history for this vendor"
                    ) {
                        setForecastData([]);
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

                const formattedData = data.points.map((point) => ({
                    day: point.day_of_week.substring(0, 3),
                    orders: point.expected_orders,
                    customers: point.expected_customers,
                    revenue: point.expected_revenue,
                }));

                const firstDate = new Date(data.points[0].date);
                const lastDate = new Date(data.points[data.points.length - 1].date);

                const formatDate = (date) =>
                    date.toLocaleDateString("en-ZA", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                    });

                setForecastPeriod(`${formatDate(firstDate)} – ${formatDate(lastDate)}`);

                setForecastData(formattedData);

                const expectedOrders = formattedData.reduce(
                    (total, item) => total + item.orders,
                    0
                );

                const expectedCustomers = formattedData.reduce(
                    (total, item) => total + item.customers,
                    0
                );

                const expectedRevenue = formattedData.reduce(
                    (total, item) => total + item.revenue,
                    0
                );

                setForecastSummary({
                    expectedOrders,
                    expectedCustomers,
                    expectedRevenue,
                });
            } catch (err) {
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
    }, [vendorId]);

    return (
        <div className="app-layout">
            <aside className="sidebar">
                <div className="brand">
                    <span className="brand-name">Byte & Bite</span>

                    <img
                        src={logo}
                        alt="Byte & Bite"
                        className="brand-logo"
                    />
                </div>

                <div className="sidebar-section">
                    <span className="sidebar-title">WORKSPACE</span>

                    <nav>
                        <a
                            href="#rush-hour-radar"
                            className="sidebar-link"
                            onClick={(event) => {
                                event.preventDefault();
                                onBack();
                            }}
                        >
                            <Clock3 size={16} />
                            Rush Hour Radar
                        </a>

                        <a
                            href="#demand-forecast"
                            className="sidebar-link active"
                        >
                            <TrendingUp size={16} />
                            Demand Forecast
                        </a>

                        <a href="#fair-comparison" className="sidebar-link">
                            <Scale size={16} />
                            Fair Comparison
                        </a>
                    </nav>
                </div>

                <div className="sidebar-section">
                    <span className="sidebar-title">Reporting</span>

                    <nav>
                        <a href="#reports" className="sidebar-link">
                            <FileText size={16} />
                            Reports
                        </a>
                    </nav>
                </div>
            </aside>

            <main className="main-content">
                <header className="topbar">
                    <div className="breadcrumb">
                        Workspace / <strong>Demand Forecast</strong>
                    </div>

                    <div className="topbar-right">
                        <button
                            className="notification-button"
                            onClick={() =>
                                (window.location.href = "/notifications")
                            }
                            aria-label="Notifications"
                            title="Notifications"
                        >
                            <Bell size={18} />
                        </button>

                        <div className="profile-container">
                            <button
                                className="user-profile"
                                onClick={() =>
                                    setProfileOpen(!profileOpen)
                                }
                                aria-label="Open user menu"
                            >
                                <div className="user-avatar">
                                    {currentUser.name.charAt(0)}
                                </div>

                                <div className="user-details">
                                    <strong>{currentUser.name}</strong>
                                    <span>{currentUser.role}</span>
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
                                        onClick={onLogout}
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
                    <div className="business-selector-row">
                        <select
                            className="business-selector"
                            value={vendorId}
                            onChange={(event) =>
                                setVendorId(event.target.value)
                            }
                            disabled={loadingVendors}
                        >
                            {loadingVendors ? (
                                <option value="">
                                    Loading businesses...
                                </option>
                            ) : (
                                vendors.map((vendor) => (
                                    <option
                                        key={vendor.vendor_id}
                                        value={vendor.vendor_id}
                                    >
                                        {vendor.name}
                                    </option>
                                ))
                            )}
                        </select>
                    </div>

                    <div className="page-heading">
                        <div>
                            <h1>Demand Forecast</h1>
                            <p>
                                View expected demand based on historical
                                transaction patterns.
                            </p>
                        </div>
                    </div>

                    {loading && <p>Loading demand forecast...</p>}

                    {error === "NO_DATA" && (
                        <p>
                            No forecast is available for this business because
                            there is no transaction history available.
                        </p>
                    )}

                    {error && error !== "NO_DATA" && (
                        <p style={{ color: "#b34c57" }}>
                            Unable to load demand forecast: {error}
                        </p>
                    )}

                    {!loading && !error && forecastData.length > 0 && (
                        <>
                            <section className="summary-grid">
                                <div className="summary-card">
                                    <span>EXPECTED TRANSACTIONS</span>
                                    <strong>
                                        {forecastSummary.expectedOrders}
                                    </strong>
                                    <small>{forecastPeriod}</small>
                                </div>

                                <div className="summary-card">
                                    <span>EXPECTED CUSTOMERS</span>
                                    <strong>
                                        {forecastSummary.expectedCustomers}
                                    </strong>
                                    <small>{forecastPeriod}</small>
                                </div>

                                <div className="summary-card">
                                    <span>EXPECTED REVENUE</span>
                                    <strong>
                                        {formatRand(
                                            forecastSummary.expectedRevenue
                                        )}
                                    </strong>
                                    <small>{forecastPeriod}</small>
                                </div>
                            </section>

                            <section className="forecast-card">
                                <div className="forecast-card-header">
                                    <div>
                                        <h2>Weekly Demand Forecast</h2>
                                        <p>
                                            Expected transactions, customers
                                            and revenue for the forecast
                                            period.
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

                                        <span>
                                            <i className="legend-revenue"></i>
                                            Revenue
                                        </span>
                                    </div>
                                </div>

                                <div className="forecast-chart">
                                    <ResponsiveContainer
                                        width="100%"
                                        height="100%"
                                    >
                                        <LineChart
                                            data={forecastData}
                                            margin={{
                                                top: 10,
                                                right: 10,
                                                left: 0,
                                                bottom: 0,
                                            }}
                                        >
                                            <CartesianGrid
                                                stroke="#edf1ef"
                                                vertical={false}
                                            />

                                            <XAxis
                                                dataKey="day"
                                                tick={{
                                                    fontSize: 11,
                                                    fill: "#7c8987",
                                                }}
                                                tickLine={false}
                                                axisLine={{
                                                    stroke: "#dfe7e4",
                                                }}
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
                                                tickFormatter={(v) =>
                                                    `R${v / 1000}k`
                                                }
                                            />

                                            <Tooltip
                                                content={<ChartTooltip />}
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
                                                activeDot={{ r: 6 }}
                                            />

                                            <Line
                                                yAxisId="left"
                                                type="monotone"
                                                dataKey="customers"
                                                stroke="#2e8f87"
                                                strokeWidth={3}
                                                dot={{ r: 3 }}
                                                activeDot={{ r: 6 }}
                                            />

                                            <Line
                                                yAxisId="right"
                                                type="monotone"
                                                dataKey="revenue"
                                                stroke="#7faaa4"
                                                strokeWidth={3}
                                                strokeDasharray="7 5"
                                                dot={{ r: 3 }}
                                                activeDot={{ r: 6 }}
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>

                                <details className="forecast-details">
                                    <summary>View daily figures</summary>

                                    <div className="table-scroll">
                                        <table className="forecast-table">
                                            <thead>
                                                <tr>
                                                    <th>Day</th>
                                                    <th>Transactions</th>
                                                    <th>Customers</th>
                                                    <th>Revenue</th>
                                                </tr>
                                            </thead>

                                            <tbody>
                                                {forecastData.map((item) => (
                                                    <tr key={item.day}>
                                                        <td>{item.day}</td>
                                                        <td>{item.orders}</td>
                                                        <td>{item.customers}</td>
                                                        <td>
                                                            {formatRand(
                                                                item.revenue
                                                            )}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </details>

                                <div className="forecast-note">
                                    Forecasts are estimates based on
                                    historical transaction patterns and may
                                    be affected by contextual factors such as
                                    holidays, exams and events.
                                </div>
                            </section>
                        </>
                    )}
                </div>
            </main>
        </div>
    );
}

export default DemandForecast;