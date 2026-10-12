import { useEffect, useRef, useState } from "react";
import logo from "./assets/Logo.png";

import {
  Bell,
  Clock3,
  TrendingUp,
  Scale,
  FileText,
  LogOut,
  ChevronDown,
  LayoutDashboard,
  CalendarDays,
  Store,
  ShieldCheck,
  Lock,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  RefreshCw,
  AlertCircle,
  Info,
} from "lucide-react";

const API_URL = "http://127.0.0.1:8000";

const RESULT_LABELS = {
  above_average: "Above average",
  average: "Around average",
  below_average: "Below average",
};

function formatNumber(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return Math.round(number).toLocaleString("en-ZA");
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
}) {
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);

  const [vendors, setVendors] = useState([]);
  const [vendorId, setVendorId] = useState("");
  const [periodMode, setPeriodMode] = useState("week");
  const [filterDate, setFilterDate] = useState("");
  const [result, setResult] = useState(null);

  const [loadingVendors, setLoadingVendors] = useState(true);
  const [loading, setLoading] = useState(false);
  const [vendorError, setVendorError] = useState("");
  const [error, setError] = useState("");

  const [reloadVendorsKey, setReloadVendorsKey] = useState(0);
  const [reloadComparisonKey, setReloadComparisonKey] = useState(0);

  const currentUser = {
    name: "User Name",
    role: "Manager",
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
      document.removeEventListener(
        "mousedown",
        handleClickOutside
      );
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

    async function loadVendors() {
      setLoadingVendors(true);
      setVendorError("");

      try {
        const response = await fetch(`${API_URL}/vendors`, {
          signal: controller.signal,
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail ||
              data.error ||
              "Could not load businesses."
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
            err.message ||
              "Could not load businesses. Please try again."
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

      if (loadingVendors || vendorError) {
        setLoading(false);
        return;
      }

      if (!vendorId) {
        setLoading(false);
        return;
      }

      if (periodMode === "day" && !filterDate) {
        setLoading(false);
        return;
      }

      setLoading(true);

      try {
        let url = `${API_URL}/vendors/${vendorId}/fair-comparison`;

        if (periodMode === "day" && filterDate) {
          url += `?filter_date=${encodeURIComponent(filterDate)}`;
        }

        const response = await fetch(url, {
          signal: controller.signal,
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail ||
              data.error ||
              "Could not load the comparison."
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

  const vendorTransactions = Number(metrics.vendor_transactions);

  const peerAverageTransactions = Number(
    metrics.peer_average_transactions
  );

  const comparisonResult = metrics.comparison_result;

  const validTransactionNumbers =
    Number.isFinite(vendorTransactions) &&
    Number.isFinite(peerAverageTransactions);

  const percentageDifference =
    validTransactionNumbers && peerAverageTransactions > 0
      ? ((vendorTransactions - peerAverageTransactions) /
          peerAverageTransactions) *
        100
      : null;

  const highestTransactionValue = Math.max(
    Number.isFinite(vendorTransactions)
      ? vendorTransactions
      : 0,
    Number.isFinite(peerAverageTransactions)
      ? peerAverageTransactions
      : 0,
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
        (peerAverageTransactions / highestTransactionValue) *
          100,
        100
      )
    : 0;

  const groupName =
    peerGroup.description ||
    (peerGroup.size_tier && peerGroup.vendor_type
      ? `${capitalise(peerGroup.size_tier)} ${peerGroup.vendor_type} group`
      : "Your comparison group");

  const participatingBusinesses =
    peerGroup.participating_businesses ??
    result?.peer_group_size;

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

  const resultClass =
    comparisonResult === "above_average"
      ? "above"
      : comparisonResult === "below_average"
        ? "below"
        : "average";

  return (
    <div className="app-layout">
      {/* Sidebar */}
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
              href="#dashboard"
              className="sidebar-link"
              onClick={(event) => {
                event.preventDefault();

                if (onDashboard) {
                  onDashboard();
                }
              }}
            >
              <LayoutDashboard size={16} />
              Dashboard
            </a>

            <a
              href="#rush-hour-radar"
              className="sidebar-link"
              onClick={(event) => {
                event.preventDefault();

                if (onBack) {
                  onBack();
                }
              }}
            >
              <Clock3 size={16} />
              Rush Hour Radar
            </a>

            <a
              href="#demand-forecast"
              className="sidebar-link"
              onClick={(event) => {
                event.preventDefault();

                if (onDemandForecast) {
                  onDemandForecast();
                }
              }}
            >
              <TrendingUp size={16} />
              Demand Forecast
            </a>

            <a
              href="#fair-comparison"
              className="sidebar-link active"
              onClick={(event) => event.preventDefault()}
            >
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

      {/* Main page */}
      <main className="main-content">
        {/* Header */}
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

            <div
              className="profile-container"
              ref={profileRef}
            >
              <button
                className="user-profile"
                onClick={() =>
                  setProfileOpen((open) => !open)
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

        {/* Fair Comparison content */}
        <div className="page-content">
          <div className="fair-content">
            <section className="fair-page-heading">
              <div>
                <div className="fair-eyebrow">
                  PERFORMANCE OVERVIEW
                </div>

                <h1>Fair Comparison</h1>

                <p>
                  See how your business compares with similar
                  businesses without revealing individual
                  competitor results.
                </p>
              </div>
            </section>

            {/* Filters */}
            <section className="fair-filter-panel">
              <div className="fair-filter-field fair-business-field">
                <label htmlFor="fair-business-select">
                  Business
                </label>

                <div className="fair-select-wrap">
                  <Store size={18} />

                  <select
                    id="fair-business-select"
                    value={vendorId}
                    onChange={(event) =>
                      setVendorId(event.target.value)
                    }
                    disabled={
                      loadingVendors || vendors.length === 0
                    }
                  >
                    {loadingVendors && (
                      <option value="">
                        Loading businesses...
                      </option>
                    )}

                    {!loadingVendors &&
                      vendors.length === 0 && (
                        <option value="">
                          No businesses available
                        </option>
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
                <label htmlFor="fair-period-select">
                  Comparison period
                </label>

                <div className="fair-select-wrap">
                  <CalendarDays size={18} />

                  <select
                    id="fair-period-select"
                    value={periodMode}
                    onChange={(event) =>
                      setPeriodMode(event.target.value)
                    }
                  >
                    <option value="week">
                      Latest 7 days of available data
                    </option>

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
                  <label htmlFor="fair-filter-date">
                    Select date
                  </label>

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

              <button
                className="fair-refresh-button"
                onClick={() =>
                  setReloadComparisonKey((value) => value + 1)
                }
                disabled={
                  loading ||
                  loadingVendors ||
                  !vendorId ||
                  (periodMode === "day" && !filterDate)
                }
                title="Refresh comparison"
              >
                <RefreshCw size={16} />
                <span>Refresh</span>
              </button>
            </section>

            {/* Selected period */}
            <div className="fair-period-summary">
              <CalendarDays size={15} />
              <span>Showing data for</span>
              <strong>{periodText}</strong>
            </div>

            {/* Business loading error */}
            {vendorError && (
              <section className="fair-message fair-message-error">
                <AlertCircle size={21} />

                <div>
                  <h2>Could not load businesses</h2>
                  <p>{vendorError}</p>

                  <button
                    className="fair-text-button"
                    onClick={() =>
                      setReloadVendorsKey(
                        (value) => value + 1
                      )
                    }
                  >
                    Try again
                  </button>
                </div>
              </section>
            )}

            {/* No businesses */}
            {!vendorError &&
              !loadingVendors &&
              vendors.length === 0 && (
                <section className="fair-message">
                  <Store size={22} />

                  <div>
                    <h2>No businesses found</h2>

                    <p>
                      There are no businesses available to
                      compare. Check that the backend has
                      returned vendor data.
                    </p>
                  </div>
                </section>
              )}

            {/* Date selection message */}
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
                      Choose a date above to view the comparison
                      for that day.
                    </p>
                  </div>
                </section>
              )}

            {/* Loading comparison */}
            {!vendorError &&
              !loadingVendors &&
              vendors.length > 0 &&
              !(periodMode === "day" && !filterDate) &&
              loading && (
                <section className="fair-message fair-message-loading">
                  <RefreshCw
                    size={22}
                    className="fair-spin"
                  />

                  <div>
                    <h2>Loading comparison</h2>

                    <p>
                      Please wait while the latest comparison
                      data is retrieved.
                    </p>
                  </div>
                </section>
              )}

            {/* Comparison error */}
            {!vendorError && !loading && error && (
              <section className="fair-message fair-message-error">
                <AlertCircle size={21} />

                <div>
                  <h2>Could not load comparison</h2>
                  <p>{error}</p>

                  <button
                    className="fair-text-button"
                    onClick={() =>
                      setReloadComparisonKey(
                        (value) => value + 1
                      )
                    }
                  >
                    Try again
                  </button>
                </div>
              </section>
            )}

            {/* Suppressed comparison */}
            {!loading &&
              !error &&
              !vendorError &&
              result?.status === "suppressed" && (
                <section className="fair-message fair-message-suppressed">
                  <Lock size={22} />

                  <div>
                    <h2>
                      Not enough data to show a comparison
                    </h2>

                    <p>
                      {result.reason ||
                        "This comparison is hidden because the minimum peer-group requirement has not been met."}
                    </p>

                    <p className="fair-message-note">
                      This protects the privacy of businesses
                      in smaller groups.
                    </p>
                  </div>
                </section>
              )}

            {/* Other unavailable results */}
            {!loading &&
              !error &&
              !vendorError &&
              result &&
              result.status !== "ok" &&
              result.status !== "suppressed" && (
                <section className="fair-message">
                  <Info size={22} />

                  <div>
                    <h2>Comparison unavailable</h2>

                    <p>
                      The backend did not return a completed
                      comparison for this business and period.
                    </p>
                  </div>
                </section>
              )}

            {/* Successful comparison */}
            {!loading &&
              !error &&
              !vendorError &&
              isOk && (
                <>
                  <section className="fair-score-card">
                    <div className="fair-score-top">
                      <div>
                        <div className="fair-score-label">
                          <Scale size={17} />
                          <span>
                            YOUR COMPARISON RESULT
                          </span>
                        </div>

                        <h2>
                          {getComparisonLabel(comparisonResult)}
                        </h2>

                        <p className="fair-score-description">
                          {getComparisonDescription(
                            comparisonResult
                          )}
                        </p>
                      </div>

                      <div
                        className={`fair-result-icon ${resultClass}`}
                      >
                        {comparisonResult === "above_average" ? (
                          <ArrowUpRight size={27} />
                        ) : comparisonResult ===
                          "below_average" ? (
                          <ArrowDownRight size={27} />
                        ) : (
                          <Minus size={27} />
                        )}
                      </div>
                    </div>

                    <div className="fair-score-divider" />

                    <div className="fair-metrics-grid">
                      <div className="fair-metric">
                        <span className="fair-metric-label">
                          Your transactions
                        </span>

                        <strong>
                          {formatNumber(
                            metrics.vendor_transactions
                          )}
                        </strong>

                        <span className="fair-metric-footnote">
                          Selected business
                        </span>
                      </div>

                      <div className="fair-metric">
                        <span className="fair-metric-label">
                          Peer-group average
                        </span>

                        <strong>
                          {formatNumber(
                            metrics.peer_average_transactions
                          )}
                        </strong>

                        <span className="fair-metric-footnote">
                          Average transactions per business
                        </span>
                      </div>

                      <div className="fair-metric">
                        <span className="fair-metric-label">
                          Difference from average
                        </span>

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
                            : `${
                                percentageDifference > 0
                                  ? "+"
                                  : ""
                              }${percentageDifference.toFixed(1)}%`}
                        </strong>

                        <span className="fair-metric-footnote">
                          Based on transaction count
                        </span>
                      </div>
                    </div>
                  </section>

                  {/* Transaction comparison and peer group */}
                  <section className="fair-detail-grid">
                    <div className="fair-panel fair-performance-panel">
                      <div className="fair-panel-heading">
                        <div>
                          <h2>Transaction comparison</h2>

                          <p>
                            Your business compared with the
                            group average
                          </p>
                        </div>
                      </div>

                      <div className="fair-bars">
                        <div className="fair-bar-item">
                          <div className="fair-bar-label-row">
                            <span>Your business</span>

                            <strong>
                              {formatNumber(
                                metrics.vendor_transactions
                              )}
                            </strong>
                          </div>

                          <div className="fair-bar-track">
                            <div
                              className="fair-bar-fill fair-bar-business"
                              style={{
                                width: `${vendorBarWidth}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div className="fair-bar-item">
                          <div className="fair-bar-label-row">
                            <span>Peer-group average</span>

                            <strong>
                              {formatNumber(
                                metrics.peer_average_transactions
                              )}
                            </strong>
                          </div>

                          <div className="fair-bar-track">
                            <div
                              className="fair-bar-fill fair-bar-average"
                              style={{
                                width: `${peerBarWidth}%`,
                              }}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="fair-chart-note">
                        <Info size={15} />

                        <span>
                          Only your business and the aggregated
                          peer average are shown. Individual
                          competitor results are hidden.
                        </span>
                      </div>
                    </div>

                    <div className="fair-panel fair-group-panel">
                      <div className="fair-panel-heading">
                        <div>
                          <h2>Your peer group</h2>

                          <p>
                            Businesses with similar
                            characteristics
                          </p>
                        </div>

                        <div className="fair-group-icon">
                          <Store size={20} />
                        </div>
                      </div>

                      <div className="fair-group-name">
                        {groupName}
                      </div>

                      <div className="fair-group-detail">
                        <span>Business type</span>

                        <strong>
                          {peerGroup.vendor_type ||
                            "Not available"}
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

                      <div className="fair-group-detail">
                        <span>Participating businesses</span>

                        <strong>
                          {participatingBusinesses ??
                            "Not available"}
                        </strong>
                      </div>

                      <div className="fair-group-privacy">
                        <ShieldCheck size={17} />

                        <span>
                          Peer businesses remain anonymous in
                          this comparison.
                        </span>
                      </div>
                    </div>
                  </section>

                  {/* Guide to comparison results */}
                  <section className="fair-panel fair-guide-panel">
                    <div className="fair-panel-heading">
                      <div>
                        <h2>Understanding your result</h2>

                        <p>
                          The result is based on transaction
                          counts for the selected period.
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

                          <p>
                            More than 10% above the peer-group
                            average.
                          </p>
                        </div>
                      </div>

                      <div className="fair-guide-item">
                        <div className="fair-guide-icon average">
                          <Minus size={18} />
                        </div>

                        <div>
                          <strong>Around average</strong>

                          <p>
                            Within 10% of the peer-group
                            average.
                          </p>
                        </div>
                      </div>

                      <div className="fair-guide-item">
                        <div className="fair-guide-icon below">
                          <ArrowDownRight size={18} />
                        </div>

                        <div>
                          <strong>Below average</strong>

                          <p>
                            More than 10% below the peer-group
                            average.
                          </p>
                        </div>
                      </div>
                    </div>
                  </section>

                  {/* Privacy note */}
                  <div className="fair-privacy-note">
                    <Lock size={17} />

                    <p>
                      <strong>Privacy comes first.</strong>{" "}
                      Comparisons are only displayed when the
                      minimum peer-group requirement is met.
                      Competitor names and individual competitor
                      transaction figures are not displayed.
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
