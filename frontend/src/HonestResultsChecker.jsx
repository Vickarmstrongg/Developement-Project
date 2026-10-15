import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Download,
  XCircle,
} from "lucide-react";

const STATUS_META = {
  PASS: { icon: CheckCircle2, className: "pass", label: "PASS" },
  FAIL: { icon: XCircle, className: "fail", label: "FAIL" },
  WARNING: { icon: AlertTriangle, className: "warning", label: "WARNING" },
  "NOT CHECKED": { icon: CircleHelp, className: "not-checked", label: "NOT CHECKED" },
};

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function csvCell(value) {
  const text = value === null || value === undefined
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function downloadReport(result) {
  const columns = [
    "Status",
    "Check",
    "Scope",
    "Application result",
    "Expected result",
    "Difference",
    "Explanation",
    "Reason",
  ];
  const rows = result.checks.map((check) => [
    check.status,
    check.title,
    check.scope,
    check.application_result,
    check.expected_result,
    check.difference,
    check.explanation,
    check.reason,
  ]);
  const contents = [columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([contents], { type: "text/csv;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = "byte-and-bite-honest-results.csv";
  link.click();
  URL.revokeObjectURL(href);
}

function HonestResultsChecker({ currentUser, defaultVendorId }) {
  const [options, setOptions] = useState({
    vendor_types: [],
    vendors: [],
    event_types: [],
  });
  const [filters, setFilters] = useState({
    start_date: "",
    end_date: "",
    vendor_type: "",
    vendor_id: defaultVendorId || "",
    radar_day: "4",
    radar_hour: "12",
    fair_date: "",
    event_year: "",
    event_type: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filtersDirty, setFiltersDirty] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch("/api/honest-results/options")
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not load checker filters.");
        }
        if (active) setOptions(data);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message || "Could not load checker filters.");
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredVendors = useMemo(() => (
    filters.vendor_type
      ? options.vendors.filter(
        (vendor) => String(vendor.vendor_type_id) === filters.vendor_type
      )
      : options.vendors
  ), [filters.vendor_type, options.vendors]);

  async function runChecks(event) {
    event?.preventDefault();
    setLoading(true);
    setError("");
    setFiltersDirty(false);
    setResult(null);
    try {
      const body = Object.fromEntries(
        Object.entries(filters)
          .filter(([, value]) => value !== "")
          .map(([key, value]) => [
            key,
            ["vendor_type", "vendor_id", "radar_day", "radar_hour", "event_year"].includes(key)
              ? Number(value)
              : value,
          ])
      );
      const response = await apiFetch("/api/honest-results/run", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "The checks could not be completed.");
      }
      setResult(data);
    } catch (runError) {
      setError(runError.message || "The checks could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  function changeFilter(name, value) {
    setFilters((previous) => ({
      ...previous,
      [name]: value,
      ...(name === "vendor_type" ? { vendor_id: "" } : {}),
    }));
    if (result) setFiltersDirty(true);
  }

  return (
    <section className="honest-results-page">
          <div className="honest-heading">
            <div>
              <h2>Honest Results Checker</h2>
              <p>Compare displayed analytics with independent database checks. A result is never marked PASS when it could not be checked.</p>
            </div>
            {result && (
              <button
                className="btn-ghost honest-download"
                type="button"
                onClick={() => downloadReport(result)}
              >
                <Download size={16} /> Download CSV
              </button>
            )}
          </div>

          <form className="honest-filters panel" onSubmit={runChecks}>
            <label>
              Start date
              <input
                type="date"
                value={filters.start_date}
                max={filters.end_date || undefined}
                onChange={(event) => changeFilter("start_date", event.target.value)}
              />
            </label>
            <label>
              End date
              <input
                type="date"
                value={filters.end_date}
                min={filters.start_date || undefined}
                onChange={(event) => changeFilter("end_date", event.target.value)}
              />
            </label>
            <label>
              Vendor type
              <select
                value={filters.vendor_type}
                onChange={(event) => changeFilter("vendor_type", event.target.value)}
              >
                <option value="">All accessible types</option>
                {options.vendor_types.map((type) => (
                  <option key={type.id} value={type.id}>{type.name}</option>
                ))}
              </select>
            </label>
            <label>
              Vendor
              <select
                value={filters.vendor_id}
                onChange={(event) => changeFilter("vendor_id", event.target.value)}
              >
                <option value="">All accessible vendors</option>
                {filteredVendors.map((vendor) => (
                  <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
                ))}
              </select>
            </label>
            <label>
              Radar weekday
              <select
                value={filters.radar_day}
                onChange={(event) => changeFilter("radar_day", event.target.value)}
              >
                {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                  .map((day, index) => <option key={day} value={index}>{day}</option>)}
              </select>
            </label>
            <label>
              Radar hour
              <select
                value={filters.radar_hour}
                onChange={(event) => changeFilter("radar_hour", event.target.value)}
              >
                {[8, 12, 15, 18, 21].map((hour) => (
                  <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>
                ))}
              </select>
            </label>
            <label>
              Fair Comparison date
              <input
                type="date"
                value={filters.fair_date}
                onChange={(event) => changeFilter("fair_date", event.target.value)}
              />
            </label>
            {currentUser?.role === "Admin" && (
              <>
                <label>
                  Event year
                  <input
                    type="number"
                    min="1"
                    max="9999"
                    value={filters.event_year}
                    onChange={(event) => changeFilter("event_year", event.target.value)}
                  />
                </label>
                <label>
                  Event type
                  <select
                    value={filters.event_type}
                    onChange={(event) => changeFilter("event_type", event.target.value)}
                  >
                    <option value="">All event types</option>
                    {options.event_types.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <div className="honest-filter-actions">
              <button className="btn-primary" type="submit" disabled={loading}>
                {loading ? "Checking…" : "Run Checks"}
              </button>
              {filtersDirty && <span role="status">Filters changed — rerun the checks.</span>}
            </div>
          </form>

          {error && <div className="honest-error" role="alert">{error}</div>}

          {!result && !loading && !error && (
            <section className="panel honest-empty">
              Choose the filters, then run the checks. Database queries are read-only.
            </section>
          )}

          {loading && (
            <section className="panel honest-empty" role="status" aria-live="polite">
              Running independent checks…
            </section>
          )}

          {result && (
            <>
              <section className={`honest-summary ${result.summary.fully_passed ? "all-pass" : "needs-review"}`}>
                <div>
                  <span className="honest-overall-label">Overall result</span>
                  <strong>{result.summary.overall_status}</strong>
                  <span>Last run: {new Date(result.run_at).toLocaleString()}</span>
                </div>
                <div className="honest-counts" aria-label="Check status totals">
                  {Object.entries({
                    PASS: result.summary.pass,
                    FAIL: result.summary.fail,
                    WARNING: result.summary.warning,
                    "NOT CHECKED": result.summary.not_checked,
                  }).map(([status, count]) => (
                    <span key={status} className={`honest-count ${STATUS_META[status].className}`}>
                      <b>{count}</b> {status}
                    </span>
                  ))}
                </div>
              </section>
              <p className="honest-policy-note">
                Vendor scope: {result.privacy_policy.vendor_scope}. Revenue is {result.privacy_policy.revenue_available ? "available under this role's permissions" : "not checked or shown for this role"}. Student identifiers are never returned.
              </p>
              <section className="honest-check-list" aria-label="Validation checks">
                {result.checks.map((check) => {
                  const meta = STATUS_META[check.status];
                  const Icon = meta?.icon || CircleHelp;
                  return (
                    <article className={`honest-check-card status-${meta?.className || "not-checked"}`} key={check.id}>
                      <div className="honest-check-heading">
                        <Icon size={19} aria-hidden="true" />
                        <h2>{check.title}</h2>
                        <span className="honest-status">{check.status}</span>
                      </div>
                      <dl>
                        <div><dt>Scope / filters</dt><dd>{check.scope || "—"}</dd></div>
                        <div><dt>Application result</dt><dd>{displayValue(check.application_result)}</dd></div>
                        <div><dt>Independent / expected result</dt><dd>{displayValue(check.expected_result)}</dd></div>
                        <div><dt>Difference</dt><dd>{displayValue(check.difference)}</dd></div>
                      </dl>
                      {check.explanation && <p>{check.explanation}</p>}
                      {check.reason && <p className="honest-reason"><strong>Reason:</strong> {check.reason}</p>}
                    </article>
                  );
                })}
              </section>
            </>
          )}
    </section>
  );
}

export default HonestResultsChecker;
