import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import Login from "./Login";
import DemandForecast from "./DemandForecast";

const DAYS = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

const VENDOR_TYPES = [
  { value: "", label: "All types" },
  { value: 3, label: "Restaurant" },
  { value: 4, label: "Fast Food" },
  { value: 5, label: "Cafe / Coffee Shop" },
];

const MEAL_SLOTS = [
  { value: 8, label: "Breakfast (07:00 – 09:00)" },
  { value: 12, label: "Lunch (11:00 – 13:00)" },
  { value: 15, label: "Afternoon (14:00 – 16:00)" },
  { value: 18, label: "Dinner (17:00 – 19:00)" },
  { value: 21, label: "Evening (20:00 – 22:00)" },
];

const LEVEL_COLORS = {
  quiet: "#A77632",
  normal: "#39715C",
  busy: "#AC3E49",
  suppressed: "#BFC5C2",
};

const LEVEL_LABELS = {
  quiet: "Quiet",
  normal: "Normal",
  busy: "Busy",
};

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [view, setView] = useState("rush");

  const [day, setDay] = useState(4);
  const [hour, setHour] = useState(12);
  const [typeId, setTypeId] = useState("");
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!loggedIn || view !== "rush") return;

    setLoading(true);

    let url = `http://127.0.0.1:8000/rush-hour-radar?day=${day}&hour=${hour}`;

    if (typeId) {
      url += `&type_id=${typeId}`;
    }

    fetch(url)
      .then((res) => res.json())
      .then((data) => setVendors(data.vendors || []))
      .catch((err) => console.error("Error fetching rush hour radar:", err))
      .finally(() => setLoading(false));
  }, [day, hour, typeId, loggedIn, view]);

  if (!loggedIn) {
    return <Login onLogin={() => setLoggedIn(true)} />;
  }

  if (view === "demand") {
    return (
      <DemandForecast
        onLogout={() => setLoggedIn(false)}
        onBack={() => setView("rush")}
      />
    );
  }

  const busyCount = vendors.filter((v) => v.level === "busy").length;
  const quietCount = vendors.filter((v) => v.level === "quiet").length;
  const recCount = vendors.filter((v) => v.recommendation).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo-dot" /> Byte &amp; Bite
        </div>

        <nav>
          <div className="nav-item">Dashboard</div>

          <div
            className="nav-item active"
            onClick={() => setView("rush")}
          >
            Rush Hour Radar
          </div>

          <div
            className="nav-item"
            onClick={() => setView("demand")}
          >
            Demand Forecast
          </div>

          <div className="nav-item">Fair Comparison</div>
          <div className="nav-item">Context Checker</div>
          <div className="nav-item">Reports</div>

          <div
            className="nav-item"
            onClick={() => setLoggedIn(false)}
          >
            Logout
          </div>
        </nav>
      </aside>

      <main className="content">
        <div className="breadcrumb">MVP / OPERATIONS VIEW</div>

        <div className="page-header">
          <div>
            <h1>Rush Hour Radar</h1>
            <p className="subtitle">
              Find the busy and quiet moments across Stellenbosch before they happen.
            </p>
          </div>

          <div className="filters">
            <select
              value={day}
              onChange={(e) => setDay(Number(e.target.value))}
            >
              {DAYS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>

            <select
              value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
            >
              {MEAL_SLOTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

            <select
              value={typeId}
              onChange={(e) => setTypeId(e.target.value)}
            >
              {VENDOR_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="stat-row">
          <div className="stat-card">
            <div className="stat-label">Vendors in view</div>
            <div className="stat-value">{vendors.length}</div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Busy now</div>
            <div
              className="stat-value"
              style={{ color: LEVEL_COLORS.busy }}
            >
              {busyCount}
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Quiet now</div>
            <div
              className="stat-value"
              style={{ color: LEVEL_COLORS.quiet }}
            >
              {quietCount}
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Open recommendations</div>
            <div className="stat-value">{recCount}</div>
          </div>
        </div>

        <div className="main-grid">
          <div className="panel map-panel">
            <h3>Vendor activity map</h3>

            {loading && <p className="loading-text">Loading...</p>}

            <MapContainer
              center={[-33.9346, 18.8617]}
              zoom={14}
              style={{ height: "420px", width: "100%" }}
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              {vendors
                .filter((v) => v.lat && v.lon)
                .map((v) => (
                  <CircleMarker
                    key={v.vendor_id}
                    center={[v.lat, v.lon]}
                    radius={v.status === "suppressed" ? 7 : 14}
                    pathOptions={{
                      color:
                        LEVEL_COLORS[
                          v.status === "suppressed"
                            ? "suppressed"
                            : v.level
                        ],
                      fillColor:
                        LEVEL_COLORS[
                          v.status === "suppressed"
                            ? "suppressed"
                            : v.level
                        ],
                      fillOpacity: 0.45,
                      weight: 2,
                    }}
                  >
                    <Popup>
                      <strong>{v.name}</strong>
                      <br />

                      {v.status === "suppressed" ? (
                        <em>
                          Not enough data to show (privacy threshold)
                        </em>
                      ) : (
                        <>
                          Status: {LEVEL_LABELS[v.level]}
                          <br />
                          {v.recommendation}
                        </>
                      )}
                    </Popup>
                  </CircleMarker>
                ))}
            </MapContainer>

            <div className="legend">
              <span>
                <i style={{ background: LEVEL_COLORS.quiet }} /> Quiet
              </span>

              <span>
                <i style={{ background: LEVEL_COLORS.normal }} /> Normal
              </span>

              <span>
                <i style={{ background: LEVEL_COLORS.busy }} /> Busy
              </span>

              <span>
                <i style={{ background: LEVEL_COLORS.suppressed }} /> Suppressed
                (privacy)
              </span>
            </div>
          </div>

          <div className="panel pulse-panel">
            <h3>Vendor pulse</h3>

            <p className="panel-sub">
              Current status for the selected day/hour
            </p>

            <div className="pulse-list">
              {[...vendors]
                .sort((a, b) => {
                  if (a.status === "ok" && b.status !== "ok") return -1;
                  if (a.status !== "ok" && b.status === "ok") return 1;
                  return 0;
                })
                .map((v) => (
                  <div className="pulse-item" key={v.vendor_id}>
                    <div>
                      <div className="pulse-name">{v.name}</div>

                      <div className="pulse-meta">
                        {v.recommendation || "No action needed"}
                      </div>
                    </div>

                    <span
                      className="pulse-pill"
                      style={{
                        background: `${
                          LEVEL_COLORS[
                            v.status === "suppressed"
                              ? "suppressed"
                              : v.level
                          ]
                        }22`,
                        color:
                          LEVEL_COLORS[
                            v.status === "suppressed"
                              ? "suppressed"
                              : v.level
                          ],
                      }}
                    >
                      {v.status === "suppressed"
                        ? "No data"
                        : LEVEL_LABELS[v.level]}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        </div>

        <div className="panel recs-panel">
          <h3>Auto-generated recommendations</h3>

          <p className="panel-sub">
            Shown only when a recurring pattern crosses the threshold
          </p>

          {vendors.filter((v) => v.recommendation).length === 0 && (
            <p className="loading-text">
              No recommendations for this day/hour.
            </p>
          )}

          {vendors
            .filter((v) => v.recommendation)
            .map((v) => (
              <div className={`rec-row ${v.level}`} key={v.vendor_id}>
                <div>
                  <strong>{v.name}</strong>

                  <div className="pulse-meta">
                    {v.recommendation}
                  </div>
                </div>

                <div className="rec-actions">
                  <button className="btn-primary">
                    {v.level === "quiet"
                      ? "Run promotion"
                      : "Hold pricing"}
                  </button>

                  <button className="btn-ghost">
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
        </div>
      </main>
    </div>
  );
}

export default App;