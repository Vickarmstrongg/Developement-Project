import { useEffect, useRef, useState } from "react";
import { apiFetch, getStoredUser } from "./api";

import {
    Bell,
    Scale,
    LogOut,
    ChevronDown,
    Store,
    CalendarDays,
    ShieldCheck,
    Lock,
    ArrowUpRight,
    ArrowDownRight,
    Minus,
    RefreshCw,
    AlertCircle,
    Info,
} from "lucide-react";
import WorkspaceSidebar from "./WorkspaceSidebar";
import UsersLink from "./UsersLink";
import ReportButton from "./ReportButton";

const RESULT_LABELS = {
    above_average: "Above average",
    average: "Around average",
    below_average: "Below average",
};

function formatNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return "—";
    }

    return Math.round(value).toLocaleString("en-ZA");
}

function capitalise(value) {
    if (!value) {
        return "";
    }

    return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDate(value) {
    if (!value) {
        return "";
    }

    const parsedDate = new Date(`${value}T12:00:00`);

    if (Number.isNaN(parsedDate.getTime())) {
        return value;
    }

    return parsedDate.toLocaleDateString("en-ZA", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

function getComparisonLabel(result) {
    return RESULT_LABELS[result] || "Comparison result";
}

function getComparisonDescription(result) {
    if (result === "above_average") {
        return "Your business recorded more transactions than the peer-group average for this period.";
    }

    if (result === "below_average") {
        return "Your business recorded fewer transactions than the peer-group average for this period.";
    }

    if (result === "average") {
        return "Your business's transaction count is within the average range for this peer group.";
    }

    return "Your comparison result is available below.";
}

function FairComparison({
    onLogout,
    onBack,
    onDashboard,
    onDemandForecast,
    onContextEvents,
}) {
    const [profileOpen, setProfileOpen] = useState(false);
    const profileRef = useRef(null);

    const [vendors, setVendors] = useState([]);
    const [vendorId, setVendorId] = useState("");
    const [periodMode, setPeriodMode] = useState("week");
    const [filterDate, setFilterDate] = useState("");
    const [result, setResult] = useState(null);
    const [contextEvents, setContextEvents] = useState([]);
    const [contextEventError, setContextEventError] = useState("");

    const [loadingVendors, setLoadingVendors] = useState(true);
    const [loading, setLoading] = useState(false);
    const [vendorError, setVendorError] = useState("");
    const [error, setError] = useState("");

    const [reloadVendorsKey, setReloadVendorsKey] = useState(0);
    const [reloadComparisonKey, setReloadComparisonKey] = useState(0);

    const storedUser = getStoredUser();
    const currentUser = {
        name: storedUser?.full_name || storedUser?.email || "",
        role: storedUser?.role || "",
    };

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
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, []);

    function handleLogout() {
        setProfileOpen(false);

        if (onLogout) {
            onLogout();
        }
    }


    useEffect(() => {
        const controller = new AbortController();

        async function loadContextEvents() {
            setContextEvents([]);
            setContextEventError("");

            let periodStart;
            let periodEnd;

            if (periodMode === "day") {
                if (!filterDate) {
                    return;
                }

                periodStart = filterDate;
                periodEnd = filterDate;
            } else {
                periodStart = result?.period?.start_date;
                periodEnd = result?.period?.end_date;

                if (!periodStart || !periodEnd) {
                    return;
                }
            }

            try {
                const response = await apiFetch("/context-events", {
                    signal: controller.signal,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail || "Could not load contextual events."
                    );
                }

                const events = Array.isArray(data.events) ? data.events : [];

                const matchingEvents = events.filter((event) =>
                    event.start_date <= periodEnd &&
                    event.end_date >= periodStart
                );

                if (!controller.signal.aborted) {
                    setContextEvents(matchingEvents);
                }
            } catch (err) {
                if (err.name !== "AbortError" && !controller.signal.aborted) {
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
    }, [
        periodMode,
        filterDate,
        result?.period?.start_date,
        result?.period?.end_date,
    ]);

    useEffect(() => {
        const controller = new AbortController();

        async function loadVendors() {
            setLoadingVendors(true);
            setVendorError("");

            try {
                const response = await apiFetch("/vendors", {
                    signal: controller.signal,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail || data.error || "Could not load businesses."
                    );
                }

                const vendorList = Array.isArray(data)
                    ? data
                    : Array.isArray(data.vendors)
                        ? data.vendors
                        : [];

                setVendors(vendorList);

                if (vendorList.length === 0) {
                    setVendorId("");
                    setResult(null);
                    return;
                }

                setVendorId((currentId) => {
                    const currentVendorExists = vendorList.some(
                        (vendor) =>
                            String(vendor.vendor_id) === String(currentId)
                    );

                    if (currentVendorExists) {
                        return currentId;
                    }

                    return String(vendorList[0].vendor_id);
                });
            } catch (err) {
                if (err.name !== "AbortError") {
                    setVendorError(
                        err.message || "Could not load businesses. Please try again."
                    );
                    setVendors([]);
                    setVendorId("");
                }
            } finally {
                if (!controller.signal.aborted) {
                    setLoadingVendors(false);
                }
            }
        }

        loadVendors();

        return () => {
            controller.abort();
        };
    }, [reloadVendorsKey]);

    useEffect(() => {
        const controller = new AbortController();

        async function loadComparison() {
            setError("");
            setResult(null);

            if (loadingVendors || vendorError || !vendorId) {
                setLoading(false);
                return;
            }

            if (periodMode === "day" && !filterDate) {
                setLoading(false);
                return;
            }

            setLoading(true);

            try {
                let url = `/vendors/${vendorId}/fair-comparison`;

                if (periodMode === "day" && filterDate) {
                    url += `?filter_date=${encodeURIComponent(filterDate)}`;
                }

                const response = await apiFetch(url, {
                    signal: controller.signal,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail || data.error || "Could not load the comparison."
                    );
                }

                if (data.error) {
                    throw new Error(data.error);
                }

                setResult(data);
            } catch (err) {
                if (err.name !== "AbortError") {
                    setError(
                        err.message ||
                        "Something went wrong while loading the comparison."
                    );
                }
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            }
        }

        loadComparison();

        return () => {
            controller.abort();
        };
    }, [
        vendorId,
        periodMode,
        filterDate,
        loadingVendors,
        vendorError,
        reloadComparisonKey,
    ]);

    const isOk = result?.status === "ok";
    const metrics = result?.metrics || {};
    const peerGroup = result?.peer_group || {};
    const period = result?.period || {};

    const vendorTransactions = metrics.vendor_transactions;
    const peerAverageTransactions = metrics.peer_average_transactions;
    const comparisonResult = metrics.comparison_result;

    const hasValidComparisonResult =
        typeof comparisonResult === "string" &&
        Object.prototype.hasOwnProperty.call(RESULT_LABELS, comparisonResult);
    const validTransactionNumbers =
        typeof vendorTransactions === "number" &&
        Number.isFinite(vendorTransactions) &&
        typeof peerAverageTransactions === "number" &&
        Number.isFinite(peerAverageTransactions);
    const hasScore =
        isOk && hasValidComparisonResult && validTransactionNumbers;

    const percentageDifference =
        validTransactionNumbers && peerAverageTransactions > 0
            ? ((vendorTransactions - peerAverageTransactions) /
                peerAverageTransactions) *
            100
            : null;

    const highestTransactionValue = Math.max(
        Number.isFinite(vendorTransactions) ? vendorTransactions : 0,
        Number.isFinite(peerAverageTransactions) ? peerAverageTransactions : 0,
        1
    );

    const vendorBarWidth = validTransactionNumbers
        ? Math.min(
            (vendorTransactions / highestTransactionValue) * 100,
            100
        )
        : 0;

    const peerBarWidth = validTransactionNumbers
        ? Math.min(
            (peerAverageTransactions / highestTransactionValue) * 100,
            100
        )
        : 0;

    const groupName =
        (peerGroup.size_tier && peerGroup.vendor_type
            ? `${capitalise(peerGroup.size_tier)} ${peerGroup.vendor_type.replace(/s$/i, "")}`
            : "Your comparison group");

    const participatingBusinesses =
        peerGroup.participating_businesses ?? result?.peer_group_size;

    let periodText = "Latest available 7-day period";

    if (period.start_date && period.end_date) {
        if (period.start_date === period.end_date) {
            periodText = formatDate(period.start_date);
        } else {
            periodText = `${formatDate(period.start_date)} – ${formatDate(
                period.end_date
            )}`;
        }
    } else if (periodMode === "day" && filterDate) {
        periodText = formatDate(filterDate);
    }

    // starts here (for the trend line graph)

    const dailyTrend = Array.isArray(result?.daily_trend)
        ? result.daily_trend
        : [];

    const maxTrendValue = Math.max(
        1,
        ...dailyTrend.map((point) =>
            Math.max(
                Number(point.vendor_transactions) || 0,
                Number(point.peer_average_transactions) || 0
            )
        )
    );

    const trendPoints = dailyTrend.map((point, index) => {
        const x =
            dailyTrend.length === 1
                ? 350
                : 48 + (index * 604) / (dailyTrend.length - 1);

        const venueValue = Number(point.vendor_transactions) || 0;
        const peerValue = Number(point.peer_average_transactions) || 0;

        return {
            ...point,
            x,
            venueY: 22 + ((maxTrendValue - venueValue) / maxTrendValue) * 170,
            peerY: 22 + ((maxTrendValue - peerValue) / maxTrendValue) * 170,
            dayLabel: new Date(`${point.date}T12:00:00`).toLocaleDateString(
                "en-ZA",
                { weekday: "short" }
            ),
            dateLabel: formatDate(point.date),
        };
    });

    const venueLine = trendPoints
        .map((point, index) =>
            `${index === 0 ? "M" : "L"} ${point.x} ${point.venueY}`
        )
        .join(" ");

    const peerLine = trendPoints
        .map((point, index) =>
            `${index === 0 ? "M" : "L"} ${point.x} ${point.peerY}`
        )
        .join(" ");

    // ends here


    const selectedDateMax = Math.max(
        Number(vendorTransactions) || 0,
        Number(peerAverageTransactions) || 0,
        1
    );

    const selectedDateBars = [
        {
            label: "Your venue",
            value: Number(vendorTransactions) || 0,
            className: "fair-chart-venue-bar",
        },
        {
            label: `${groupName} average`,
            value: Number(peerAverageTransactions) || 0,
            className: "fair-chart-peer-bar",
        },
    ].map((bar, index) => ({
        ...bar,
        x: index === 0 ? 200 : 400,
        height: (bar.value / selectedDateMax) * 150,
    }));


    const resultClass =
        comparisonResult === "above_average"
            ? "above"
            : comparisonResult === "below_average"
                ? "below"
                : "average";

    return (
        <div className="app-layout">
            <WorkspaceSidebar
                activeView="fair"
                onNavigate={(view) => ({
                    dashboard: onDashboard,
                    rush: onBack,
                    demand: onDemandForecast,
                    context: onContextEvents,
                }[view]?.())}
            />

            <main className="main-content">
                <header className="topbar">
                    <div className="breadcrumb">
                        Workspace / <strong>Fair Comparison</strong>
                    </div>

                    <div className="topbar-right">
                        <button
                            className="notification-button"
                            onClick={() => {
                                window.location.href = "/notifications";
                            }}
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
                                    {currentUser.name.charAt(0)}
                                </div>

                                <div className="user-details">
                                    <strong>{currentUser.name}</strong>
                                    <span>{currentUser.role}</span>
                                </div>

                                <ChevronDown size={14} className="profile-chevron" />
                            </button>

                            {profileOpen && (
                                <div className="profile-dropdown">
                                     
                                    <button className="logout-option" onClick={handleLogout}>
                                        <LogOut size={15} />
                                        Log Out
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                <div className="page-content">
                    <div className="fair-content">
                        <section className="fair-page-heading report-heading">
                            <div className="fair-heading-copy">
                                <h1>Fair Comparison Score</h1>
                                <p>
                                    See how your business compares with similar businesses.
                                </p>
                            </div>

                            <div className="fair-filter-panel">
                                <div className="fair-filter-field fair-business-field">
                                    <label htmlFor="fair-business-select">Business</label>

                                    <div className="fair-select-wrap">
                                        <Store size={18} />

                                        <select
                                            id="fair-business-select"
                                            value={vendorId}
                                            onChange={(event) => setVendorId(event.target.value)}
                                            disabled={loadingVendors || vendors.length === 0}
                                        >
                                            {loadingVendors && (
                                                <option value="">Loading businesses...</option>
                                            )}

                                            {!loadingVendors && vendors.length === 0 && (
                                                <option value="">No businesses available</option>
                                            )}

                                            {vendors.map((vendor) => (
                                                <option
                                                    key={vendor.vendor_id}
                                                    value={String(vendor.vendor_id)}
                                                >
                                                    {vendor.name}
                                                </option>
                                            ))}
                                        </select>

                                        <ChevronDown
                                            size={16}
                                            className="fair-select-chevron"
                                        />
                                    </div>
                                </div>

                                <div className="fair-filter-field fair-period-field">
                                    <label htmlFor="fair-period-select">Period</label>

                                    <div className="fair-select-wrap">
                                        <CalendarDays size={18} />

                                        <select
                                            id="fair-period-select"
                                            value={periodMode}
                                            onChange={(event) =>
                                                setPeriodMode(event.target.value)
                                            }
                                        >
                                            <option value="week">Latest 7 days</option>
                                            <option value="day">Specific date</option>
                                        </select>

                                        <ChevronDown
                                            size={16}
                                            className="fair-select-chevron"
                                        />
                                    </div>
                                </div>



                                {periodMode === "day" && (
                                    <div className="fair-filter-field fair-date-field">
                                        <label htmlFor="fair-filter-date">Date</label>

                                        <input
                                            id="fair-filter-date"
                                            type="date"
                                            value={filterDate}
                                            onChange={(event) =>
                                                setFilterDate(event.target.value)
                                            }
                                        />
                                    </div>
                                )}


                            </div>
                            {hasScore && (
                                <ReportButton
                                    title="Fair Comparison"
                                    subtitle={`${result?.vendor_name || ""} · ${periodText}`}
                                    reportType="fair_comparison"
                                    vendorId={vendorId}
                                    periodStart={period.start_date}
                                    periodEnd={period.end_date}
                                />
                            )}
                        </section>

                        <div className="fair-period-summary">
                            <CalendarDays size={15} />
                            <span>Showing data for</span>
                            <strong>{periodText}</strong>
                        </div>

                        {vendorError && (
                            <section className="fair-message fair-message-error">
                                <AlertCircle size={21} />
                                <div>
                                    <h2>Could not load businesses</h2>
                                    <p>{vendorError}</p>
                                    <button
                                        className="fair-text-button"
                                        onClick={() =>
                                            setReloadVendorsKey((value) => value + 1)
                                        }
                                    >
                                        Try again
                                    </button>
                                </div>
                            </section>
                        )}

                        {!vendorError && !loadingVendors && vendors.length === 0 && (
                            <section className="fair-message">
                                <Store size={22} />
                                <div>
                                    <h2>No businesses found</h2>
                                    <p>
                                        There are no businesses available to compare. Check that
                                        the backend has returned vendor data.
                                    </p>
                                </div>
                            </section>
                        )}

                        {!vendorError &&
                            !loadingVendors &&
                            vendors.length > 0 &&
                            periodMode === "day" &&
                            !filterDate && (
                                <section className="fair-message">
                                    <CalendarDays size={22} />
                                    <div>
                                        <h2>Select a date</h2>
                                        <p>
                                            Choose a date above to view the comparison for that day.
                                        </p>
                                    </div>
                                </section>
                            )}

                        {!vendorError &&
                            !loadingVendors &&
                            vendors.length > 0 &&
                            !(periodMode === "day" && !filterDate) &&
                            loading && (
                                <section className="fair-message fair-message-loading">
                                    <RefreshCw size={22} className="fair-spin" />
                                    <div>
                                        <h2>Loading comparison</h2>
                                        <p>
                                            Please wait while the latest comparison data is
                                            retrieved.
                                        </p>
                                    </div>
                                </section>
                            )}

                        {!vendorError && !loading && error && (
                            <section className="fair-message fair-message-error">
                                <AlertCircle size={21} />
                                <div>
                                    <h2>Could not load comparison</h2>
                                    <p>{error}</p>
                                    <button
                                        className="fair-text-button"
                                        onClick={() =>
                                            setReloadComparisonKey((value) => value + 1)
                                        }
                                    >
                                        Try again
                                    </button>
                                </div>
                            </section>
                        )}

                        {!loading &&
                            !error &&
                            !vendorError &&
                            result?.status === "suppressed" && (
                                <section className="fair-message fair-message-suppressed">
                                    <Lock size={22} />
                                    <div>
                                        <h2>Not enough data to show a comparison</h2>
                                        <p>
                                            {result.reason ||
                                                "This comparison is hidden because the minimum peer-group requirement has not been met."}
                                        </p>
                                        <p className="fair-message-note">
                                            This protects the privacy of businesses in smaller
                                            groups.
                                        </p>
                                    </div>
                                </section>
                            )}

                        {!loading &&
                            !error &&
                            !vendorError &&
                            result &&
                            (result.status !== "ok" || !hasScore) &&
                            result.status !== "suppressed" && (
                                <section className="fair-message">
                                    <Info size={22} />
                                    <div>
                                        <h2>Comparison unavailable</h2>
                                        <p>
                                            {result.status === "ok"
                                                ? "The response is missing a valid comparison result or transaction metrics."
                                                : "The backend did not return a completed comparison for this business and period."}
                                        </p>
                                    </div>
                                </section>
                            )}

                        {!loading && !error && !vendorError && hasScore && (
                            <>
                                <section className="fair-score-card">
                                    <div className="fair-score-left">
                                        <div className="fair-score-label">
                                            <Scale size={17} />
                                            <span>YOUR COMPARISON RESULT</span>
                                        </div>

                                        <div className="fair-score-main">
                                            <div>
                                                <h2 className={`fair-result-heading ${resultClass}`}>
                                                    {getComparisonLabel(comparisonResult)}
                                                </h2>

                                                <p className="fair-score-description">
                                                    {getComparisonDescription(comparisonResult)}
                                                </p>
                                            </div>

                                            <div className={`fair-result-icon ${resultClass}`}>
                                                {comparisonResult === "above_average" ? (
                                                    <ArrowUpRight size={27} />
                                                ) : comparisonResult === "below_average" ? (
                                                    <ArrowDownRight size={27} />
                                                ) : (
                                                    <Minus size={27} />
                                                )}
                                            </div>
                                        </div>

                                        <div className="fair-big-row">
                                            <strong className="fair-big-number">
                                                {formatNumber(metrics.vendor_transactions)}
                                            </strong>
                                            <span className="fair-big-label">transactions</span>
                                        </div>

                                        <p className="fair-small">
                                            Transactions recorded for your business during this period
                                        </p>

                                        <div className="fair-bar-block">
                                            <div className="fair-bar-label-row">
                                                <span>Your business</span>
                                                <strong>
                                                    {formatNumber(metrics.vendor_transactions)}
                                                </strong>
                                            </div>
                                            <div className="fair-bar-track">
                                                <div
                                                    className="fair-bar-fill fair-bar-business"
                                                    style={{ width: `${vendorBarWidth}%` }}
                                                />
                                            </div>
                                        </div>

                                        <div className="fair-bar-block">
                                            <div className="fair-bar-label-row">
                                                <span>Peer-group average</span>
                                                <strong>
                                                    {formatNumber(metrics.peer_average_transactions)}
                                                </strong>
                                            </div>
                                            <div className="fair-bar-track">
                                                <div
                                                    className="fair-bar-fill fair-bar-average"
                                                    style={{ width: `${peerBarWidth}%` }}
                                                />
                                            </div>
                                        </div>

                                        <div className="fair-difference">
                                            <span>Difference from peer average</span>
                                            <strong
                                                className={
                                                    percentageDifference === null
                                                        ? ""
                                                        : percentageDifference > 0
                                                            ? "fair-positive"
                                                            : percentageDifference < 0
                                                                ? "fair-negative"
                                                                : ""
                                                }
                                            >
                                                {percentageDifference === null
                                                    ? "—"
                                                    : `${percentageDifference > 0 ? "+" : ""}${percentageDifference.toFixed(1)}%`}
                                            </strong>
                                        </div>

                                        <p className="fair-footnote">
                                            Figures show your transaction count and the aggregated
                                            peer average. Individual competitor results are not shown.
                                        </p>
                                    </div>

                                    <div className="fair-score-right">
                                        <div className="fair-group-top">
                                            <div>
                                                <span className="fair-eyebrow-small">
                                                    YOUR COMPARISON GROUP
                                                </span>
                                                <h2>{groupName}</h2>
                                            </div>
                                            <div className="fair-group-icon">
                                                <Store size={20} />
                                            </div>
                                        </div>

                                        <div className="fair-group-count">
                                            <div>
                                                <strong>
                                                    {participatingBusinesses ?? "—"}
                                                </strong>
                                                <p>participating businesses</p>
                                            </div>
                                            <span className="fair-eligible">
                                                <ShieldCheck size={14} />
                                                Eligible group
                                            </span>
                                        </div>

                                        <div className="fair-group-detail">
                                            <span>Business type</span>
                                            <strong>
                                                {peerGroup.vendor_type || "Not available"}
                                            </strong>
                                        </div>

                                        <div className="fair-group-detail">
                                            <span>Operational size</span>
                                            <strong>
                                                {peerGroup.size_tier
                                                    ? capitalise(peerGroup.size_tier)
                                                    : "Not available"}
                                            </strong>
                                        </div>
                                    </div>
                                </section>

                                {/* starts here */}


                                <section className="fair-comparison-layout">
                                    <section className="fair-panel fair-trend-panel">
                                        <div className="fair-panel-heading">
                                            <div>
                                                <h2>Your venue &amp; shared pattern</h2>
                                                <p>
                                                    {periodMode === "day"
                                                        ? "Compare transaction counts for the selected date."
                                                        : "A quick view of venue activity beside the aggregated peer trend."}
                                                </p>
                                            </div>

                                            <span className="fair-trend-badge">
                                                {periodMode === "day" ? "Selected date" : "7-day trend"}
                                            </span>
                                        </div>

                                        {dailyTrend.length > 0 ? (
                                            <>
                                                <div className="fair-trend-legend">
                                                    <span>
                                                        <span className="fair-legend-line fair-legend-venue" />
                                                        Your venue
                                                    </span>

                                                    <span>
                                                        <span className="fair-legend-line fair-legend-peer" />
                                                        {groupName} average
                                                    </span>
                                                </div>

                                                <div className="fair-trend-chart">
                                                    {periodMode === "day" ? (
                                                        <>
                                                            <svg
                                                                viewBox="0 0 700 240"
                                                                role="img"
                                                                aria-label={`Bar chart for ${formatDate(filterDate)}, comparing your venue's ${formatNumber(vendorTransactions)} transactions with the peer-group average of ${formatNumber(peerAverageTransactions)} transactions`}
                                                                preserveAspectRatio="xMidYMid meet"
                                                            >
                                                                {[0, 1, 2, 3].map((line) => {
                                                                    const y = 30 + line * 50;

                                                                    return (
                                                                        <line
                                                                            key={line}
                                                                            x1="70"
                                                                            y1={y}
                                                                            x2="630"
                                                                            y2={y}
                                                                            className="fair-chart-gridline"
                                                                        />
                                                                    );
                                                                })}

                                                                {selectedDateBars.map((bar) => {
                                                                    const barY = 190 - bar.height;

                                                                    return (
                                                                        <g key={bar.label}>
                                                                            <rect
                                                                                x={bar.x}
                                                                                y={barY}
                                                                                width="100"
                                                                                height={bar.height}
                                                                                rx="5"
                                                                                className={bar.className}
                                                                            />

                                                                            <text
                                                                                x={bar.x + 50}
                                                                                y={Math.max(barY - 10, 18)}
                                                                                textAnchor="middle"
                                                                                className="fair-chart-value"
                                                                            >
                                                                                {formatNumber(bar.value)}
                                                                            </text>

                                                                            <text
                                                                                x={bar.x + 50}
                                                                                y="215"
                                                                                textAnchor="middle"
                                                                                className="fair-chart-day"
                                                                            >
                                                                                {bar.label === "Your venue"
                                                                                    ? "Your venue"
                                                                                    : "Peer average"}
                                                                            </text>
                                                                        </g>
                                                                    );
                                                                })}

                                                                <text
                                                                    x="350"
                                                                    y="237"
                                                                    textAnchor="middle"
                                                                    className="fair-chart-date"
                                                                >
                                                                    {formatDate(filterDate)}
                                                                </text>
                                                            </svg>


                                                        </>
                                                    ) : (
                                                        <svg
                                                            viewBox="0 0 700 240"
                                                            role="img"
                                                            aria-label="Line chart comparing your venue's daily transactions with the aggregated peer average"
                                                            preserveAspectRatio="xMidYMid meet"
                                                        >
                                                            {[0, 1, 2, 3].map((line) => {
                                                                const y = 22 + line * (170 / 3);

                                                                return (
                                                                    <line
                                                                        key={line}
                                                                        x1="38"
                                                                        y1={y}
                                                                        x2="662"
                                                                        y2={y}
                                                                        className="fair-chart-gridline"
                                                                    />
                                                                );
                                                            })}

                                                            {trendPoints.length > 1 && (
                                                                <>
                                                                    <path
                                                                        d={peerLine}
                                                                        className="fair-chart-peer-line"
                                                                    />

                                                                    <path
                                                                        d={venueLine}
                                                                        className="fair-chart-venue-line"
                                                                    />
                                                                </>
                                                            )}

                                                            {trendPoints.map((point) => (
                                                                <g key={point.date}>
                                                                    <circle
                                                                        cx={point.x}
                                                                        cy={point.peerY}
                                                                        r="4"
                                                                        className="fair-chart-peer-point"
                                                                    />

                                                                    <circle
                                                                        cx={point.x}
                                                                        cy={point.venueY}
                                                                        r="4.5"
                                                                        className="fair-chart-venue-point"
                                                                    />

                                                                    <text
                                                                        x={point.x}
                                                                        y="218"
                                                                        textAnchor="middle"
                                                                        className="fair-chart-day"
                                                                    >
                                                                        {point.dayLabel}
                                                                    </text>
                                                                </g>
                                                            ))}
                                                        </svg>
                                                    )}
                                                </div>
                                            </>


                                        ) : (
                                            <div className="fair-trend-empty">
                                                Daily trend data is not available for this period.
                                            </div>
                                        )}


                                        {(periodMode === "day" || periodMode === "week") && (
                                            <div className="fair-context-events">
                                                <div className="fair-context-heading">
                                                    <CalendarDays size={18} />
                                                    <strong>
                                                        {periodMode === "day"
                                                            ? "Context recorded for this date"
                                                            : "Context recorded for the last 7 days"}
                                                    </strong>
                                                </div>

                                                {contextEventError ? (
                                                    <p className="fair-context-error" role="status">
                                                        {contextEventError}
                                                    </p>
                                                ) : contextEvents.length > 0 ? (
                                                    contextEvents.map((event) => (
                                                        <article
                                                            className="fair-context-event"
                                                            key={event.event_id}
                                                        >
                                                            <strong>{event.name}</strong>
                                                            <span>{event.event_type}</span>
                                                            <small>
                                                                {formatDate(event.start_date)}
                                                                {event.start_date !== event.end_date &&
                                                                    ` – ${formatDate(event.end_date)}`}
                                                            </small>
                                                        </article>
                                                    ))
                                                ) : (
                                                    <p>
                                                        No contextual events have been recorded for this period.
                                                    </p>
                                                )}

                                                <p className="fair-context-disclaimer">
                                                    These events provide background context only. Their presence
                                                    does not establish that they caused the transaction pattern.
                                                </p>
                                            </div>
                                        )}

                                    </section>

                                    <div className="fair-comparison-side">
                                        <section className="fair-panel fair-understanding-panel">
                                            <div className="fair-panel-heading">
                                                <div>
                                                    <h2>Understanding your result</h2>
                                                    <p>
                                                        Your result is based on transaction counts for the
                                                        selected period.
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="fair-guide-grid">
                                                <div className="fair-guide-item">
                                                    <div className="fair-guide-icon above">
                                                        <ArrowUpRight size={18} />
                                                    </div>
                                                    <div>
                                                        <strong>Above average</strong>
                                                        <p>More than 10% above the peer-group average.</p>
                                                    </div>
                                                </div>

                                                <div className="fair-guide-item">
                                                    <div className="fair-guide-icon average">
                                                        <Minus size={18} />
                                                    </div>
                                                    <div>
                                                        <strong>Around average</strong>
                                                        <p>Within 10% of the peer-group average.</p>
                                                    </div>
                                                </div>

                                                <div className="fair-guide-item">
                                                    <div className="fair-guide-icon below">
                                                        <ArrowDownRight size={18} />
                                                    </div>
                                                    <div>
                                                        <strong>Below average</strong>
                                                        <p>More than 10% below the peer-group average.</p>
                                                    </div>
                                                </div>
                                            </div>
                                        </section>

                                        <section className="fair-panel fair-privacy-panel">
                                            <div className="fair-panel-heading">
                                                <div className="fair-group-icon">
                                                    <ShieldCheck size={20} />
                                                </div>
                                                <div>
                                                    <h2>A fair comparison</h2>
                                                    <p>Like-for-like groups. Private by design.</p>
                                                </div>
                                            </div>

                                            <ul className="fair-list">
                                                <li>
                                                    Peers are grouped by business type and operational scale.
                                                </li>
                                                <li>
                                                    A comparison is only shown when the minimum peer-group
                                                    requirement is met.
                                                </li>
                                                <li>
                                                    The result shows an above, around or below-average
                                                    comparison, not a ranking.
                                                </li>
                                            </ul>
                                        </section>
                                    </div>
                                </section>


                                {/* ends here */}

                                <div className="fair-privacy-note">
                                    <Lock size={17} />
                                    <p>
                                        <strong>Privacy comes first.</strong> Comparisons use
                                        aggregated values and are hidden when the minimum
                                        peer-group requirement is not met.
                                    </p>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}

export default FairComparison;
