import { useEffect, useRef, useState } from "react";
import {
  Bell,
  LogOut,
  ChevronDown,
} from "lucide-react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import Login from "./Login";
import DemandForecast from "./DemandForecast";
import WeeklyActivityEvidence from "./WeeklyActivity";
import FairComparison from "./FairComparison";
import ContextEvents from "./ContextEvents";
import Dashboard from "./DashboardPage";
import SetPassword from "./SetPassword";
import Reports from "./Reports";
import { apiFetch, clearSession, getStoredUser, getToken } from "./api";
import WorkspaceSidebar from "./WorkspaceSidebar";
import Users from "./Users";
import UsersLink from "./UsersLink";
import ReportButton from "./ReportButton";
import ForgotPassword from "./ForgotPassword";

const HASH_TO_VIEW = {
  "#dashboard": "dashboard",
  "#rush-hour-radar": "rush",
  "#demand-forecast": "demand",
  "#fair-comparison": "fair",
  "#context-events": "context",
  "#weekly-activity-evidence": "evidence",
  "#users": "users",
  "#reports": "reports",
};

const VIEW_TO_HASH = Object.fromEntries(
  Object.entries(HASH_TO_VIEW).map(([hash, view]) => [view, hash])
);

function viewFromHash(hash = window.location.hash) {
  return HASH_TO_VIEW[hash] || "dashboard";
}

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

function TrackpadMapPan() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();

    const handleWheel = (event) => {
      if (event.ctrlKey) {
        event.preventDefault();

        const point = map.mouseEventToContainerPoint(event);
        const zoomChange = -event.deltaY * 0.07;

        map.setZoomAround(
          point,
          map.getZoom() + zoomChange
        );
      } else {
        event.preventDefault();

        map.panBy(
          [-event.deltaX, -event.deltaY],
          { animate: false }
        );
      }
    };

    container.addEventListener("wheel", handleWheel, {
      passive: false,
    });

    return () => {
      container.removeEventListener("wheel", handleWheel);
    };
  }, [map]);

  return null;
}

function ResetMapButton() {
  const map = useMap();

  const resetMap = () => {
    map.setView([-33.9346, 18.8617], 13, {
      animate: true,
    });
  };

  return (
    <button
      type="button"
      className="reset-map-button"
      onClick={resetMap}
    >
      Reset map
    </button>
  );
}

function App() {
  const [sessionUser, setSessionUser] = useState(() =>
    getToken() ? getStoredUser() : null
  );
  const loggedIn = sessionUser !== null;

  const [view, setView] = useState(() => viewFromHash());
  const [evidenceDetails, setEvidenceDetails] = useState(null);

  const [day, setDay] = useState(4);
  const [hour, setHour] = useState(12);
  const [typeId, setTypeId] = useState("");
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [recommendationPage, setRecommendationPage] = useState(1);
  const recommendationsPerPage = 15;

  const [profileOpen, setProfileOpen] = useState(false);

  const profileRef = useRef(null);

  const currentUser = {
    ...sessionUser,
    name: sessionUser?.full_name || sessionUser?.email || "",
  };

  function navigateTo(nextView) {
    setView(nextView);
    const hash = VIEW_TO_HASH[nextView];
    if (hash && window.location.hash !== hash) {
      window.location.hash = hash;
    }
  }

  function openWeeklyEvidence(details) {
    setEvidenceDetails(details);
    navigateTo("evidence");
  }

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

  useEffect(() => {
    const onExpired = () => {
      setSessionUser(null);
      setView("dashboard");
    };

    window.addEventListener("bb-logout", onExpired);
    return () => window.removeEventListener("bb-logout", onExpired);
  }, []);

  useEffect(() => {
    document.body.dataset.role = sessionUser?.role || "";
  }, [sessionUser]);

  useEffect(() => {
    const onHash = () => {
      const nextView = viewFromHash();
      if (nextView !== "dashboard" || window.location.hash === "#dashboard") {
        setView(nextView);
      }
      if (window.location.hash === "#users" && getStoredUser()?.role === "Admin") {
        setView("users");
      }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!loggedIn || view !== "rush") return;

    setLoading(true);

    let url = `/rush-hour-radar?day=${day}&hour=${hour}`;

    if (typeId) {
      url += `&type_id=${typeId}`;
    }

    apiFetch(url)
      .then((res) => res.json())
      .then((data) => setVendors(data.vendors || []))
      .catch((err) =>
        console.error("Error fetching rush hour radar:", err)
      )
      .finally(() => setLoading(false));
  }, [day, hour, typeId, loggedIn, view]);

  useEffect(() => {
    setRecommendationPage(1);
  }, [day, hour, typeId]);


  function handleLogout() {
    clearSession();
    setProfileOpen(false);
    setSessionUser(null);
    setView("dashboard");
  }

  if (window.location.pathname === "/set-password") {
    return <SetPassword />;
  }
  if (window.location.pathname === "/forgot-password") {
    return <ForgotPassword />;
  }
  if (!loggedIn) {
    return (
      <Login
        onLogin={(user) => {
          setProfileOpen(false);
          setView(viewFromHash());
          setSessionUser(user);
        }}
      />
    );
  }

  if (view === "evidence" && evidenceDetails) {
    return (
      <WeeklyActivityEvidence
        vendorId={evidenceDetails.vendorId}
        vendorName={evidenceDetails.vendorName}
        selectedDate={evidenceDetails.selectedDate}
        metric={evidenceDetails.metric}
        onBack={() => navigateTo("demand")}
        onLogout={handleLogout}
        onDashboard={() => navigateTo("dashboard")}
        onFairComparison={() => navigateTo("fair")}
        onContextEvents={() => navigateTo("context")}
      />
    );
  }
  if (view === "users") {
    if (sessionUser?.role !== "Admin") {
      return <div>Access denied</div>;
    }

    return (
      <Users
        currentUser={currentUser}
        onDashboard={() => navigateTo("dashboard")}
        onRushHourRadar={() => navigateTo("rush")}
        onDemandForecast={() => navigateTo("demand")}
        onFairComparison={() => navigateTo("fair")}
        onContextEvents={() => navigateTo("context")}
        onLogout={handleLogout}
      />
    );
  }

  if (view === "reports") {
    return (
      <Reports
        currentUser={currentUser}
        onNavigate={navigateTo}
        onLogout={handleLogout}
      />
    );
  }


  if (view === "demand") {
    return (
      <DemandForecast
        onLogout={handleLogout}
        onBack={() => navigateTo("rush")}
        onDashboard={() => navigateTo("dashboard")}
        onFairComparison={() => navigateTo("fair")}
        onContextEvents={() => navigateTo("context")}
        onOpenWeeklyEvidence={openWeeklyEvidence}
      />
    );
  }

  if (view === "fair") {
    return (
      <FairComparison
        onLogout={handleLogout}
        onBack={() => navigateTo("rush")}
        onDashboard={() => navigateTo("dashboard")}
        onDemandForecast={() => navigateTo("demand")}
        onContextEvents={() => navigateTo("context")}
      />
    );
  }

  if (view === "context") {
    return (
      <ContextEvents
        currentUser={currentUser}
        onNavigate={navigateTo}
        onLogout={handleLogout}
      />
    );
  }

  if (view === "dashboard") {
    return (
      <div className="app-layout">

        <WorkspaceSidebar activeView="dashboard" onNavigate={navigateTo} />

        <main className="main-content">

          <header className="topbar">
            <div className="breadcrumb">
              Workspace / <strong>Dashboard</strong>
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
                    <UsersLink />
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

          <Dashboard
            onContextEvents={() => navigateTo("context")}
            onRushHourRadar={() => navigateTo("rush")}
            onDemandForecast={() => navigateTo("demand")}
          />

        </main>
      </div>
    );
  }

  const recommendations = vendors.filter(
    (v) => v.recommendation
  );

  const totalRecommendationPages = Math.ceil(
    recommendations.length / recommendationsPerPage
  );

  const startIndex =
    (recommendationPage - 1) * recommendationsPerPage;

  const sortedRecommendations = [...recommendations].sort(
    (a, b) => {
      const priority = (v) => v.level === "quiet" ? 1 : 2;
      return priority(a) - priority(b);
    }
  );

  const visibleRecommendations = sortedRecommendations.slice(
    startIndex,
    startIndex + recommendationsPerPage
  );

  const busyCount = vendors.filter(
    (v) => v.level === "busy"
  ).length;

  const quietCount = vendors.filter(
    (v) => v.level === "quiet"
  ).length;

  const recCount = vendors.filter(
    (v) => v.recommendation
  ).length;

  return (
    <div className="app-layout">

      <WorkspaceSidebar activeView="rush" onNavigate={navigateTo} />

      <main className="main-content">

        <header className="topbar">
          <div className="breadcrumb">
            Workspace / <strong>Rush Hour Radar</strong>
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
                  <UsersLink />
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

        <div className="rush-content">

          <div className="rush-page-header">
            <div>
              <h1>Rush Hour Radar</h1>

              <p className="rush-subtitle">
                Find the busy and quiet moments across Stellenbosch before they happen.
              </p>

            </div>

            <div className="filters">
              <select
                value={day}
                onChange={(e) =>
                  setDay(Number(e.target.value))
                }
              >
                {DAYS.map((d) => (
                  <option
                    key={d.value}
                    value={d.value}
                  >
                    {d.label}
                  </option>
                ))}
              </select>

              <select
                value={hour}
                onChange={(e) =>
                  setHour(Number(e.target.value))
                }
              >
                {MEAL_SLOTS.map((s) => (
                  <option
                    key={s.value}
                    value={s.value}
                  >
                    {s.label}
                  </option>
                ))}
              </select>

              <select
                value={typeId}
                onChange={(e) =>
                  setTypeId(e.target.value)
                }
              >
                {VENDOR_TYPES.map((t) => (
                  <option
                    key={t.value}
                    value={t.value}
                  >
                    {t.label}
                  </option>
                ))}
              </select>
              {!loading && vendors.length > 0 && (
                <ReportButton
                  title="Rush Hour Radar"
                  subtitle={`${DAYS.find((d) => d.value === day)?.label} · ${MEAL_SLOTS.find((s) => s.value === hour)?.label} · ${VENDOR_TYPES.find((t) => String(t.value) === String(typeId))?.label}`}
                  reportType="rush_hour_radar"
                />
              )}
            </div>
          </div>

          <div className="stat-row">

            <div className="stat-card">
              <div className="stat-label">
                Vendors in view
              </div>

              <div className="stat-value">
                {vendors.length}
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-label">
                Busy now
              </div>

              <div
                className="stat-value"
                style={{
                  color: LEVEL_COLORS.busy,
                }}
              >
                {busyCount}
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-label">
                Quiet now
              </div>

              <div
                className="stat-value"
                style={{
                  color: LEVEL_COLORS.quiet,
                }}
              >
                {quietCount}
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-label">
                Open recommendations
              </div>

              <div className="stat-value">
                {recCount}
              </div>
            </div>

          </div>

          <div className="main-grid">

            <div className="panel map-panel">

              <h3>Vendor activity map</h3>

              {loading && (
                <p className="loading-text">
                  Loading...
                </p>
              )}

              <MapContainer
                className="rush-map"
                center={[-33.9346, 18.8617]}
                zoom={14}
                minZoom={12}
                maxZoom={16}
                scrollWheelZoom={false}
                touchZoom={true}
                zoomSnap={0.25}
              >

                <TrackpadMapPan />
                <ResetMapButton />

                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                {vendors
                  .filter((v) => v.lat && v.lon)
                  .map((v) => (
                    <CircleMarker
                      key={v.vendor_id}
                      center={[
                        v.lat,
                        v.lon,
                      ]}
                      radius={
                        v.status === "suppressed"
                          ? 7
                          : 14
                      }
                      pathOptions={{
                        color:
                          LEVEL_COLORS[
                          v.status ===
                            "suppressed"
                            ? "suppressed"
                            : v.level
                          ],
                        fillColor:
                          LEVEL_COLORS[
                          v.status ===
                            "suppressed"
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
                            Not enough data to show
                            (privacy threshold)
                          </em>
                        ) : (
                          <>
                            Status:{" "}
                            {LEVEL_LABELS[v.level]}

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
                  <i
                    style={{
                      background:
                        LEVEL_COLORS.quiet,
                    }}
                  />
                  Quiet
                </span>

                <span>
                  <i
                    style={{
                      background:
                        LEVEL_COLORS.normal,
                    }}
                  />
                  Normal
                </span>

                <span>
                  <i
                    style={{
                      background:
                        LEVEL_COLORS.busy,
                    }}
                  />
                  Busy
                </span>

                <span>
                  <i
                    style={{
                      background:
                        LEVEL_COLORS.suppressed,
                    }}
                  />
                  Suppressed (privacy)
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
                    if (
                      a.status === "ok" &&
                      b.status !== "ok"
                    ) {
                      return -1;
                    }

                    if (
                      a.status !== "ok" &&
                      b.status === "ok"
                    ) {
                      return 1;
                    }

                    return 0;
                  })
                  .map((v) => (
                    <div
                      className="pulse-item"
                      key={v.vendor_id}
                    >
                      <div>
                        <div className="pulse-name">
                          {v.name}
                        </div>

                        <div className="pulse-meta">
                          {v.recommendation ||
                            "No action needed"}
                        </div>
                      </div>

                      <span
                        className="pulse-pill"
                        style={{
                          background: `${LEVEL_COLORS[
                            v.status ===
                              "suppressed"
                              ? "suppressed"
                              : v.level
                          ]
                            }22`,

                          color:
                            LEVEL_COLORS[
                            v.status ===
                              "suppressed"
                              ? "suppressed"
                              : v.level
                            ],
                        }}
                      >
                        {v.status ===
                          "suppressed"
                          ? "No data"
                          : LEVEL_LABELS[
                          v.level
                          ]}
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

            {recommendations.length === 0 && (
              <p className="loading-text">
                No recommendations for this day/hour.
              </p>
            )}

            {visibleRecommendations
              .map((v) => (
                <div
                  className={`rec-row ${v.level}`}
                  key={v.vendor_id}
                >
                  <div>
                    <strong>{v.name}</strong>

                    <div className="pulse-meta">
                      {v.recommendation}
                    </div>
                  </div>

                  <div className="rec-actions">
                    <span className="recommendation-label">
                      {v.level === "quiet"
                        ? "Run promotion"
                        : "Hold pricing"}
                    </span>

                    <span className="recommendation-label dismiss-label">
                      Dismiss
                    </span>
                  </div>
                </div>
              ))}

            {totalRecommendationPages > 1 && (
              <div className="recommendation-pagination">
                <button
                  type="button"
                  disabled={recommendationPage === 1}
                  onClick={() =>
                    setRecommendationPage((page) => page - 1)
                  }
                >
                  Previous
                </button>

                <span>
                  Page {recommendationPage} of {totalRecommendationPages}
                </span>

                <button
                  type="button"
                  disabled={
                    recommendationPage === totalRecommendationPages
                  }
                  onClick={() =>
                    setRecommendationPage((page) => page + 1)
                  }
                >
                  Next
                </button>
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}

export default App;