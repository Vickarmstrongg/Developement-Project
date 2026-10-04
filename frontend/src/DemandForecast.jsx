import logo from "./assets/Logo.png";
import {
    Bell,
    Clock3,
    TrendingUp,
    Scale,
    FileText,
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

function DemandForecast() {
    const currentUser = {
        name: "User Name",
        role: "Manager",
    };

    const forecastSummary = {
        expectedOrders: 1240,
        expectedCustomers: 1080,
        expectedRevenue: 61600,
    };

    const forecastData = [
        { day: "Mon", orders: 170, customers: 150, revenue: 7200 },
        { day: "Tue", orders: 180, customers: 160, revenue: 7800 },
        { day: "Wed", orders: 190, customers: 170, revenue: 8200 },
        { day: "Thu", orders: 200, customers: 180, revenue: 8900 },
        { day: "Fri", orders: 210, customers: 190, revenue: 9500 },
        { day: "Sat", orders: 220, customers: 200, revenue: 9800 },
        { day: "Sun", orders: 230, customers: 210, revenue: 10200 },
    ];
    // Temporary data - remove when connected to backend 

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
                        <a href="#rush-hour-radar" className="sidebar-link">
                            <Clock3 size={16} />
                            Rush Hour Radar
                        </a>

                        <a href="#demand-forecast" className="sidebar-link active">
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
                            onClick={() => window.location.href = "/notifications"}
                            aria-label="Notifications"
                            title="Notifications"
                        >
                            <Bell size={18} />
                        </button>


                        <div className="user-profile">

                            <div className="user-avatar">
                                {currentUser.name.charAt(0)}
                            </div>

                            <div className="user-details">
                                <strong>{currentUser.name}</strong>
                                <span>{currentUser.role}</span>
                            </div>
                        </div>
                    </div>
                </header>

                <div className="page-content">

                    <div className="business-selector-row">
                        <select className="business-selector">
                            <option>All Businesses</option>
                            <option>Vendor 1</option>
                            <option>Vendor 2</option>
                        </select>
                    </div>

                    <div className="page-heading">

                        <div>
                            <h1>Demand Forecast</h1>
                            <p>View expected demand for your business over the next seven days.</p>
                        </div>
                    </div>

                    <section className="summary-grid">

                        <div className="summary-card">
                            <span>EXPECTED TRANSACTIONS</span>
                            <strong>
                                {forecastSummary.expectedOrders}
                            </strong>
                            <small>
                                Next 7 days
                            </small>
                        </div>

                        <div className="summary-card">
                            <span>EXPECTED CUSTOMERS</span>
                            <strong>
                                {forecastSummary.expectedCustomers}
                            </strong>
                            <small>
                                Next 7 days
                            </small>
                        </div>

                        <div className="summary-card">
                            <span>EXPECTED REVENUE</span>
                            <strong>
                                {formatRand(forecastSummary.expectedRevenue)}
                            </strong>
                            <small>
                                Weekly forecast
                            </small>
                        </div>
                    </section>

                    <section className="forecast-card">
                        <div className="forecast-card-header">
                            <div>
                                <h2>Weekly Demand Forecast</h2>
                                <p>Expected transactions, customers and revenue for the next seven days.</p>
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
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart
                                    data={forecastData}
                                    margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                                >
                                    <CartesianGrid stroke="#edf1ef" vertical={false} />

                                    <XAxis
                                        dataKey="day"
                                        tick={{ fontSize: 11, fill: "#7c8987" }}
                                        tickLine={false}
                                        axisLine={{ stroke: "#dfe7e4" }}
                                    />

                                    <YAxis
                                        yAxisId="left"
                                        tick={{ fontSize: 11, fill: "#7c8987" }}
                                        tickLine={false}
                                        axisLine={false}
                                        width={40}
                                    />

                                    <YAxis
                                        yAxisId="right"
                                        orientation="right"
                                        tick={{ fontSize: 11, fill: "#7c8987" }}
                                        tickLine={false}
                                        axisLine={false}
                                        width={48}
                                        tickFormatter={(v) => `R${v / 1000}k`}
                                    />

                                    <Tooltip
                                        content={<ChartTooltip />}
                                        cursor={{ stroke: "#c9d6d2" }}
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
                                                <td>{formatRand(item.revenue)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </details>

                        <div className="forecast-note">
                            Forecasts are estimates based on historical transaction patterns and may be affected by contextual factors such as holidays, exams and events.
                        </div>
                    </section>
                </div >
            </main >
        </div >
    );
}
export default DemandForecast;