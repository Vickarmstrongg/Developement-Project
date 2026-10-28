
import { useEffect, useRef, useState } from "react";
import {
    ArrowLeft,
    Bell,
    CalendarDays,
    ChevronDown,
    Info,
    LogOut,
    TrendingDown,
    TrendingUp,
} from "lucide-react";
import {
    Bar,
    BarChart,
    CartesianGrid,
    Legend,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import { apiFetch, getStoredUser } from "./api";
import WorkspaceSidebar from "./WorkspaceSidebar";

function WeeklyActivityEvidence({
    vendorId,
    vendorName,
    selectedDate,
    metric = "revenue",
    onBack,
    onLogout,
    onDashboard,
    onFairComparison,
    onContextEvents,
}) {
    const [evidence, setEvidence] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const storedUser = getStoredUser();

    const currentUser = {
        name: storedUser?.full_name || storedUser?.email || "User",
        role: storedUser?.role || "",
    };

    const [profileOpen, setProfileOpen] = useState(false);
    const profileRef = useRef(null);

    useEffect(() => {
        function handleClickOutside(event) {
            if (
                profileRef.current &&
                !profileRef.current.contains(event.target)
            ) {
                setProfileOpen(false);
            }
        }

        document.addEventListener("mousedown", handleClickOutside);

        return () => {
            document.removeEventListener(
                "mousedown",
                handleClickOutside
            );
        };
    }, []);

    function handleLogout() {
        setProfileOpen(false);
        onLogout?.();
    }

    useEffect(() => {
        async function loadEvidence() {
            if (!vendorId || !selectedDate) {
                setError("The business or selected date is missing.");
                setLoading(false);
                return;
            }

            try {
                setLoading(true);
                setError("");

                const response = await apiFetch(
                    `/vendors/${vendorId}/demand-forecast?selected_date=${selectedDate}`
                );

                if (!response.ok) {
                    throw new Error(
                        "Could not load weekly activity evidence."
                    );
                }

                const data = await response.json();

                if (!data.historical_comparison) {
                    throw new Error(
                        "Historical activity comparison is not available."
                    );
                }

                setEvidence(data.historical_comparison);
            } catch (err) {
                console.error(
                    "Error loading weekly evidence:",
                    err
                );

                setError(
                    err.message ||
                    "Could not load weekly activity evidence."
                );
            } finally {
                setLoading(false);
            }
        }

        loadEvidence();
    }, [vendorId, selectedDate]);

    const days = evidence?.days || [];

    const isRevenue = metric === "revenue";

    const activityTitle = isRevenue
        ? "Weekly Activity for Revenue"
        : "Weekly Activity for Transactions";

    const activityLabel = isRevenue
        ? "revenue"
        : "transactions";


    function formatActivityValue(value) {
        if (value == null || value === "") return "N/A";

        if (isRevenue) {
            const totalCents = Math.round(Number(value) * 100);
            const whole = Math.floor(totalCents / 100);
            const cents = totalCents % 100;

            const formattedWhole = new Intl.NumberFormat("en-US", {
                useGrouping: true,
                maximumFractionDigits: 0,
            }).format(whole).split(",").join(" ");

            return `R ${formattedWhole}.${String(cents).padStart(2, "0")}`;
        }

        return Number(value).toLocaleString("en-ZA", {
            maximumFractionDigits: 0,
        });
    }

    const chartData = days.map((day) => ({
        day: day.day_of_week?.substring(0, 3) || "",
        fullDay: day.day_of_week || "",
        date: day.date,
        thisWeek: isRevenue
            ? day.this_week_revenue
            : day.this_week_orders,
        previousWeek: isRevenue
            ? day.previous_week_revenue
            : day.previous_week_orders,
    }));

    const selectedWeekTotal = chartData.reduce(
        (total, day) =>
            total + (Number(day.thisWeek) || 0),
        0
    );

    const previousWeekTotal = chartData.reduce(
        (total, day) =>
            total + (Number(day.previousWeek) || 0),
        0
    );

    const overallChange =
        previousWeekTotal > 0
            ? (
                (selectedWeekTotal - previousWeekTotal) /
                previousWeekTotal
            ) * 100
            : null;

    const highestActivityDay = chartData
        .filter((day) => day.thisWeek != null)
        .reduce(
            (highest, day) =>
                !highest ||
                    Number(day.thisWeek) > Number(highest.thisWeek)
                    ? day
                    : highest,
            null
        );

    const largestDecreaseDay = chartData
        .filter(
            (day) =>
                day.thisWeek != null &&
                day.previousWeek != null &&
                Number(day.thisWeek) < Number(day.previousWeek)
        )
        .reduce(
            (largest, day) =>
                !largest ||
                    Number(day.thisWeek) - Number(day.previousWeek) <
                    Number(largest.thisWeek) - Number(largest.previousWeek)
                    ? day
                    : largest,
            null
        );

    function formatDate(value, includeYear = false) {
        if (!value) return "N/A";

        return new Date(`${value}T12:00:00`).toLocaleDateString(
            "en-ZA",
            {
                day: "numeric",
                month: "short",
                ...(includeYear ? { year: "numeric" } : {}),
            }
        );
    }

    function formatPercentage(value) {
        return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
    }

    return (
        <div className="app-layout">
            <WorkspaceSidebar
                activeView="demand"
                onNavigate={(nextView) => {
                    if (nextView === "dashboard") {
                        onDashboard?.();
                    }

                    if (nextView === "demand") {
                        onBack?.();
                    }

                    if (nextView === "fair") {
                        onFairComparison?.();
                    }

                    if (nextView === "context") {
                        onContextEvents?.();
                    }
                }}
            />

            <main className="main-content">
                <header className="topbar">
                    <div className="breadcrumb">
                        Workspace / Demand Forecast /{" "}
                        <strong>Weekly Activity</strong>
                    </div>

                    <div className="topbar-right">
                        <button
                            type="button"
                            className="notification-button"
                            aria-label="Notifications"
                            title="Notifications"
                        >
                            <Bell size={18} />
                        </button>

                        <div
                            className="profile-container"
                            ref={profileRef}
                        >
                            <button
                                type="button"
                                className="user-profile"
                                onClick={() =>
                                    setProfileOpen((open) => !open)
                                }
                                aria-label="Open user menu"
                                aria-expanded={profileOpen}
                            >
                                <div className="user-avatar">
                                    {currentUser.name
                                        .charAt(0)
                                        .toUpperCase()}
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
                                        type="button"
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

                <div className="rush-content evidence-page">
                    <button
                        type="button"
                        className="back-to-forecast"
                        onClick={onBack}
                    >
                        <ArrowLeft size={22} />
                        Back
                    </button>

                    <div className="evidence-page-title">
                        <div>
                            <h1>{activityTitle}</h1>

                            {evidence && (
                                <p>
                                    {formatDate(
                                        evidence.selected_week_start
                                    )}
                                    {" – "}
                                    {formatDate(
                                        evidence.selected_week_end
                                    )}
                                    {" compared with "}
                                    {formatDate(
                                        evidence.previous_week_start
                                    )}
                                    {" – "}
                                    {formatDate(
                                        evidence.previous_week_end
                                    )}
                                </p>
                            )}

                            {!evidence && (
                                <p>
                                    Actual recorded {activityLabel} for{" "}
                                    {vendorName || "the selected business"}.
                                </p>
                            )}
                        </div>
                    </div>

                    {loading && (
                        <p className="loading-text">
                            Loading weekly activity...
                        </p>
                    )}

                    {!loading && error && (
                        <div className="panel">
                            <p>{error}</p>
                        </div>
                    )}

                    {!loading && !error && evidence && (
                        <div className="weekly-evidence-grid">
                            <div className="weekly-evidence-main">
                                <section className="panel evidence-chart-panel">
                                    <div className="evidence-chart-legend">
                                        <span>
                                            <i className="evidence-legend-selected" />
                                            Selected week
                                        </span>

                                        <span>
                                            <i className="evidence-legend-previous" />
                                            Previous week
                                        </span>
                                    </div>

                                    <div className="evidence-chart">
                                        <ResponsiveContainer
                                            width="100%"
                                            height="100%"
                                        >
                                            <BarChart
                                                data={chartData}
                                                margin={{
                                                    top: 10,
                                                    right: 8,
                                                    left: 0,
                                                    bottom: 5,
                                                }}
                                                barCategoryGap="24%"
                                                barGap={3}
                                            >
                                                <CartesianGrid
                                                    stroke="#e2edf5"
                                                    vertical={false}
                                                />

                                                <XAxis
                                                    dataKey="day"
                                                    tick={{
                                                        fontSize: 11,
                                                        fill: "#244765",
                                                    }}
                                                    tickLine={false}
                                                    axisLine={{
                                                        stroke: "#dce8f1",
                                                    }}
                                                />

                                                <YAxis
                                                    allowDecimals={isRevenue}
                                                    tick={{
                                                        fontSize: 10,
                                                        fill: "#52718c",
                                                    }}
                                                    tickLine={false}
                                                    axisLine={false}
                                                    width={36}
                                                />

                                                <Tooltip
                                                    labelFormatter={(
                                                        label,
                                                        payload
                                                    ) => {
                                                        const item =
                                                            payload?.[0]
                                                                ?.payload;

                                                        return item
                                                            ? `${item.fullDay} ${formatDate(
                                                                item.date
                                                            )}`
                                                            : label;
                                                    }}
                                                    formatter={(value, name) => [
                                                        formatActivityValue(value),
                                                        name,
                                                    ]}
                                                    contentStyle={{
                                                        borderRadius: 8,
                                                        border: "1px solid #dce8f1",
                                                        fontSize: 12,
                                                    }}
                                                />

                                                <Legend
                                                    content={() => null}
                                                />

                                                <Bar
                                                    dataKey="thisWeek"
                                                    name="Selected week"
                                                    fill="#087d83"
                                                    radius={[
                                                        1,
                                                        1,
                                                        0,
                                                        0,
                                                    ]}
                                                    maxBarSize={30}
                                                    isAnimationActive={false}
                                                />

                                                <Bar
                                                    dataKey="previousWeek"
                                                    name="Previous week"
                                                    fill="#829eae"
                                                    radius={[
                                                        1,
                                                        1,
                                                        0,
                                                        0,
                                                    ]}
                                                    maxBarSize={30}
                                                    isAnimationActive={false}
                                                />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                </section>

                                <div className="evidence-total-cards">
                                    <section className="panel evidence-total-card">
                                        <div className="evidence-total-icon">
                                            <CalendarDays size={19} />
                                        </div>

                                        <div>
                                            <span>Selected week total</span>

                                            <strong>
                                                {formatActivityValue(selectedWeekTotal)}
                                            </strong>

                                            <small>
                                                Recorded {activityLabel}
                                            </small>
                                        </div>
                                    </section>

                                    <section className="panel evidence-total-card">
                                        <div className="evidence-total-icon previous">
                                            <CalendarDays size={19} />
                                        </div>

                                        <div>
                                            <span>Previous week total</span>

                                            <strong>
                                                {formatActivityValue(previousWeekTotal)}
                                            </strong>

                                            <small
                                                className={
                                                    overallChange == null
                                                        ? ""
                                                        : overallChange > 0
                                                            ? "evidence-change-positive"
                                                            : overallChange < 0
                                                                ? "evidence-change-negative"
                                                                : ""
                                                }
                                            >
                                                {overallChange == null ? (
                                                    "Overall change unavailable"
                                                ) : (
                                                    <>
                                                        {overallChange > 0 ? (
                                                            <TrendingUp
                                                                size={14}
                                                            />
                                                        ) : overallChange < 0 ? (
                                                            <TrendingDown
                                                                size={14}
                                                            />
                                                        ) : null}

                                                        {formatPercentage(
                                                            overallChange
                                                        )}
                                                        {" overall"}
                                                    </>
                                                )}
                                            </small>
                                        </div>
                                    </section>
                                </div>
                            </div>

                            <aside className="panel evidence-highlights-panel">
                                <h2>Historical Highlights</h2>

                                {highestActivityDay && (
                                    <div className="evidence-summary-card">
                                        <div className="evidence-summary-icon increase">
                                            <TrendingUp size={21} />
                                        </div>

                                        <div>
                                            <span>
                                                Highest activity
                                            </span>

                                            <strong>{highestActivityDay.fullDay}</strong>

                                            <p>
                                                {formatActivityValue(highestActivityDay.thisWeek)}{" "} recorded {activityLabel} <br /> in the selected week.
                                            </p>
                                        </div>
                                    </div>
                                )}

                                {largestDecreaseDay && (
                                    <div className="evidence-summary-card">
                                        <div className="evidence-summary-icon decrease">
                                            <TrendingDown size={21} />
                                        </div>

                                        <div>
                                            <span>
                                                Largest decrease
                                            </span>

                                            <strong>{largestDecreaseDay.fullDay}</strong>

                                            <p>
                                                {formatActivityValue(largestDecreaseDay.thisWeek)}{" "} compared with{" "} {formatActivityValue(largestDecreaseDay.previousWeek)}{" "} for the previous weekday.
                                            </p>
                                        </div>
                                    </div>
                                )}

                                {!largestDecreaseDay && (
                                    <div className="evidence-summary-card">
                                        <div className="evidence-summary-icon increase">
                                            <TrendingUp size={21} />
                                        </div>

                                        <div>
                                            <span>
                                                Week-on-week activity
                                            </span>

                                            <strong>
                                                No daily decrease
                                            </strong>

                                            <p>
                                                No day had lower {activityLabel} than the corresponding previous weekday.
                                            </p>
                                        </div>
                                    </div>
                                )}

                                <div className="evidence-summary-card interpretation">
                                    <div className="evidence-summary-icon info">
                                        <Info size={21} />
                                    </div>

                                    <div>
                                        <span>
                                            How to interpret this
                                        </span>

                                        <p>
                                            This comparison shows a difference in recorded loyalty {activityLabel}. It does not establish what caused the change.
                                        </p>
                                    </div>
                                </div>
                            </aside>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}

export default WeeklyActivityEvidence;
