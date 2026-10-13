import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CalendarDays,
  Clock3,
  RefreshCw,
  Store,
  TrendingUp,
  Users,
  Utensils,
  Wallet,
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
import { apiFetch } from "./api";

function formatNumber(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-ZA", { maximumFractionDigits: 0 })
    : "—";
}

function formatCurrency(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-ZA", {
        style: "currency",
        currency: "ZAR",
        maximumFractionDigits: 0,
      })
    : "Unavailable";
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-ZA", {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="dashboard-tooltip">
      <strong>{formatDate(label)}</strong>
      {point.status === "suppressed" ? (
        <span>Transactions hidden for privacy</span>
      ) : (
        <span>{formatNumber(point.transactions)} transactions</span>
      )}
      {typeof point.revenue === "number" && (
        <span>{formatCurrency(point.revenue)} revenue</span>
      )}
    </div>
  );
}

function KpiCard({ title, value, detail, icon: Icon, tone = "green" }) {
  return (
    <article className="dashboard-kpi panel">
      <div className={`dashboard-kpi-icon ${tone}`}><Icon size={18} /></div>
      <div className="dashboard-kpi-copy">
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function DashboardPage({ onContextEvents, onRushHourRadar }) {
  const [filters, setFilters] = useState({
    start_date: "",
    end_date: "",
    vendor_type: "",
    vendor_id: "",
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const skipDefaultRequest = useRef(null);

  useEffect(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([name, value]) => {
      if (value) params.set(name, value);
    });
    const query = params.toString();
    if (skipDefaultRequest.current !== null && skipDefaultRequest.current === query) {
      skipDefaultRequest.current = null;
      return undefined;
    }

    const controller = new AbortController();
    async function loadDashboard() {
      setLoading(true);
      setError("");
      setData(null);
      try {
        const response = await apiFetch(
          `/api/dashboard/overview${query ? `?${query}` : ""}`,
          { signal: controller.signal }
        );
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.detail || `Could not load dashboard (${response.status}).`);
        }
        setData(result);
        if (!filters.start_date && !filters.end_date && result.date_range?.start) {
          const defaults = new URLSearchParams({
            start_date: result.date_range.start,
            end_date: result.date_range.end,
          });
          skipDefaultRequest.current = defaults.toString();
          setFilters((current) => ({
            ...current,
            start_date: result.date_range.start,
            end_date: result.date_range.end,
          }));
        }
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setError(requestError.message || "Could not load the dashboard.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadDashboard();
    return () => controller.abort();
  }, [filters, refreshKey]);

  const options = data?.filter_options || { vendor_types: [], vendors: [] };
  const vendors = filters.vendor_type
    ? options.vendors.filter(
        (vendor) => String(vendor.vendor_type_id) === filters.vendor_type
      )
    : options.vendors;
  const kpis = data?.kpis || {};
  const trend = data?.demand_trend || [];
  const heatmap = data?.demand_heatmap;
  const heatmapMaximum = Math.max(
    0,
    ...(heatmap?.values || []).flatMap((day) =>
      day.cells
        .filter((cell) => cell.status === "available")
        .map((cell) => cell.transactions)
    )
  );

  function changeFilter(name, value) {
    setFilters((current) => ({
      ...current,
      [name]: value,
      ...(name === "vendor_type" ? { vendor_id: "" } : {}),
    }));
  }

  return (
    <div className="dashboard-page page-content">
      <div className="dashboard-heading-row">
        <div className="page-heading">
          <h1>Dashboard</h1>
          <p>Your overview of student food demand and vendor performance.</p>
        </div>
        <button
          className="btn-ghost dashboard-refresh"
          type="button"
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
        >
          <RefreshCw size={15} /> Refresh
        </button>
      </div>

      <section className="dashboard-filters panel" aria-label="Dashboard filters">
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
            <option value="">All vendor types</option>
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
            <option value="">All vendors</option>
            {vendors.map((vendor) => (
              <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
            ))}
          </select>
        </label>
        {data?.date_range?.start && (
          <p className="dashboard-range">
            Showing {formatDate(data.date_range.start)} – {formatDate(data.date_range.end)}
          </p>
        )}
      </section>

      {data?.access_mode === "local_preview" && (
        <div className="dashboard-preview-notice" role="status">
          Local preview mode: dashboard data is available without backend
          authentication. Revenue remains hidden.
        </div>
      )}

      {data?.privacy_policy?.review_required && (
        <div className="dashboard-privacy-notice" role="status">
          <AlertCircle size={17} />
          <span>{data.privacy_policy.notice}</span>
        </div>
      )}

      {error && (
        <section className="dashboard-state dashboard-error" role="alert">
          <AlertCircle size={20} />
          <div>
            <strong>Dashboard unavailable</strong>
            <p>{error}</p>
            {error.includes("Authentication") && (
              <p>
                Trusted backend authentication is not configured. The temporary
                frontend login does not authenticate API requests.
              </p>
            )}
            <button
              className="btn-ghost"
              type="button"
              onClick={() => setRefreshKey((key) => key + 1)}
            >
              Try again
            </button>
          </div>
        </section>
      )}

      {loading && !data && !error && (
        <section className="dashboard-state panel" aria-live="polite">
          <RefreshCw size={18} className="dashboard-spinning" />
          <span>Loading dashboard data…</span>
        </section>
      )}

      {data && !data.sample_data && (
        <>
          {loading && <p className="dashboard-refreshing" aria-live="polite">Updating results…</p>}
          <section className="dashboard-kpi-grid" aria-label="Key metrics">
            <KpiCard
              title="Transactions"
              value={kpis.status === "available" ? formatNumber(kpis.total_transactions) : "Unavailable"}
              detail={kpis.status === "suppressed" ? "Hidden for privacy" : "Historical actuals"}
              icon={Utensils}
            />
            <KpiCard
              title="Distinct customers"
              value={kpis.status === "available" ? formatNumber(kpis.distinct_customers) : "Unavailable"}
              detail={kpis.status === "suppressed" ? "Hidden for privacy" : "Unique students in period"}
              icon={Users}
              tone="amber"
            />
            {Object.prototype.hasOwnProperty.call(kpis, "revenue") && (
              <KpiCard
                title="Revenue"
                value={formatCurrency(kpis.revenue)}
                detail={data.permissions?.can_view_revenue ? "Historical actuals" : "Unavailable"}
                icon={Wallet}
              />
            )}
            <KpiCard
              title="Busiest observed period"
              value={data.service_outlook?.status === "available"
                ? data.service_outlook.title.replace("Historically busiest: ", "")
                : "Unavailable"}
              detail="Historical, not a forecast"
              icon={Clock3}
              tone="red"
            />
            <KpiCard
              title="Vendors covered"
              value={formatNumber(kpis.vendors_covered)}
              detail="With transactions in this range"
              icon={Store}
            />
          </section>

          <section className="dashboard-main-grid">
            <article className="dashboard-panel panel">
              <div className="dashboard-section-heading">
                <div>
                  <h2>Demand trend</h2>
                  <p>Daily transactions in the selected period</p>
                </div>
                <TrendingUp size={18} />
              </div>
              {trend.length ? (
                <div className="dashboard-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trend} margin={{ top: 8, right: 12, left: -14, bottom: 2 }}>
                      <CartesianGrid stroke="#e9efec" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={formatDate}
                        minTickGap={25}
                        tick={{ fontSize: 10, fill: "#758683" }}
                        tickLine={false}
                        axisLine={{ stroke: "#dfe7e4" }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 10, fill: "#758683" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip content={<TrendTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="transactions"
                        name="Transactions"
                        stroke="#2d9088"
                        strokeWidth={2.5}
                        dot={{ r: 2 }}
                        activeDot={{ r: 5 }}
                        connectNulls={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="dashboard-empty">No transaction data for this date range.</div>
              )}
              <p className="dashboard-chart-note">
                Daily values below the current privacy threshold are hidden.
              </p>
            </article>

            <article className="dashboard-panel panel">
              <div className="dashboard-section-heading">
                <div>
                  <h2>Demand by day and time</h2>
                  <p>Historical transactions · Monday-first weekdays</p>
                </div>
                <Clock3 size={18} />
              </div>
              {heatmap?.values?.length ? (
                <>
                  <div className="dashboard-heatmap-scroll">
                    <div className="dashboard-heatmap">
                      <span className="dashboard-heatmap-corner" />
                      {heatmap.periods.map((period) => (
                        <span className="dashboard-heatmap-period" key={period.label}>{period.label}</span>
                      ))}
                      {heatmap.values.map((day) => (
                        <div className="dashboard-heatmap-row" key={day.day}>
                          <strong>{day.day.slice(0, 3)}</strong>
                          {day.cells.map((cell, index) => (
                            <span
                              key={`${day.day}-${index}`}
                              className={`dashboard-heat-cell ${cell.status} ${
                                cell.status === "available"
                                  ? cell.transactions / Math.max(heatmapMaximum, 1) >= 0.67
                                    ? "high"
                                    : cell.transactions / Math.max(heatmapMaximum, 1) >= 0.34
                                      ? "medium"
                                      : "low"
                                  : ""
                              }`}
                              title={cell.status === "available"
                                ? `${day.day}, ${heatmap.periods[index].label}: ${formatNumber(cell.transactions)} transactions`
                                : `${day.day}, ${heatmap.periods[index].label}: ${cell.status === "suppressed" ? "hidden for privacy" : "no data"}`}
                              aria-label={cell.status === "available"
                                ? `${day.day} ${heatmap.periods[index].label}: ${formatNumber(cell.transactions)} transactions`
                                : `${day.day} ${heatmap.periods[index].label}: ${cell.status}`}
                            >
                              {cell.status === "available" ? formatNumber(cell.transactions) : "—"}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="dashboard-heat-legend">
                    <span><i className="low" /> Lower</span>
                    <span><i className="high" /> Higher</span>
                    <span><i className="hidden" /> Hidden / no data</span>
                  </div>
                </>
              ) : (
                <div className="dashboard-empty">Heatmap is unavailable for this selection.</div>
              )}
            </article>
          </section>

          <section className="dashboard-lower-grid">
            <article className="dashboard-panel dashboard-outlook panel">
              <div className="dashboard-section-heading">
                <div>
                  <span className="dashboard-eyebrow">SERVICE OUTLOOK</span>
                  <h2>{data.service_outlook?.title || "No historical insight available"}</h2>
                </div>
                <Clock3 size={19} />
              </div>
              {data.service_outlook?.status === "available" ? (
                <>
                  <p>{data.service_outlook.recommendation}</p>
                  <small>{data.service_outlook.source} This is historical, not a forecast.</small>
                </>
              ) : (
                <p>{data.service_outlook?.reason || "No privacy-safe insight is available."}</p>
              )}
            </article>

            <article className="dashboard-panel panel">
              <div className="dashboard-section-heading">
                <div>
                  <span className="dashboard-eyebrow">RUSH HOUR RADAR</span>
                  <h2>Latest reference period</h2>
                </div>
                <button className="dashboard-text-link" type="button" onClick={onRushHourRadar}>
                  Open Radar
                </button>
              </div>
              {data.rush_hour_radar?.status === "available" ? (
                <>
                  <p className="dashboard-radar-date">
                    {formatDate(data.rush_hour_radar.reference_date)} · {data.rush_hour_radar.reference_period}
                  </p>
                  <div className="dashboard-radar-stats">
                    <span className="busy"><strong>{formatNumber(data.rush_hour_radar.busy)}</strong> Busy</span>
                    <span className="normal"><strong>{formatNumber(data.rush_hour_radar.normal)}</strong> Normal</span>
                    <span className="quiet"><strong>{formatNumber(data.rush_hour_radar.quiet)}</strong> Quiet</span>
                  </div>
                  <small>
                    Uses the existing Rush Hour Radar classifications; privacy-suppressed statuses are omitted.
                  </small>
                </>
              ) : (
                <div className="dashboard-empty">{data.rush_hour_radar?.reason || "Radar summary unavailable."}</div>
              )}
            </article>

            <article className="dashboard-panel panel dashboard-events-panel">
              <div className="dashboard-section-heading">
                <div>
                  <span className="dashboard-eyebrow">CALENDAR</span>
                  <h2>Upcoming context events</h2>
                </div>
                <button className="dashboard-text-link" type="button" onClick={onContextEvents}>
                  Open calendar
                </button>
              </div>
              {data.upcoming_context_events?.length ? (
                <ul className="dashboard-event-list">
                  {data.upcoming_context_events.map((event) => (
                    <li key={event.event_id}>
                      <CalendarDays size={16} />
                      <div>
                        <strong>{event.name}</strong>
                        <span>{event.event_type} · {formatDate(event.start_date)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="dashboard-empty">
                  No calendar events overlap the 30 days after the selected period.
                </div>
              )}
            </article>
          </section>
          <p className="dashboard-data-note">
            Values come from stored transactions. Customer-level records and identifiers are never returned.
          </p>
        </>
      )}
    </div>
  );
}

export default DashboardPage;
