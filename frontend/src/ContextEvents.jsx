import { useEffect, useRef, useState } from "react";
import {
  Bell,
  CalendarDays,
  ChevronDown,
  Clock3,
  FileText,
  LayoutDashboard,
  LogOut,
  Plus,
  RefreshCw,
  Scale,
  TrendingUp,
  Trash2,
} from "lucide-react";
import logo from "./assets/Logo.png";

const API = "http://127.0.0.1:8000/context-events";

function ContextEvents({
  currentUser,
  onDashboard,
  onDemandForecast,
  onFairComparison,
  onLogout,
  onRushHourRadar,
}) {
const [events, setEvents] = useState([]);
const [types, setTypes] = useState([]);
const [year, setYear] = useState(new Date().getFullYear());
const [filterType, setFilterType] = useState("");
const [loading, setLoading] = useState(true);
const [saving, setSaving] = useState(false);
const [error, setError] = useState("");
const [editingId, setEditingId] = useState(null);
const [profileOpen, setProfileOpen] = useState(false);
const profileRef = useRef(null);
const user = currentUser || { name: "User Name", role: "Manager" };

const emptyForm = {
name: "",
event_type: "",
start_date: "",
end_date: "",
};

const [form, setForm] = useState(emptyForm);

useEffect(() => {
  function handleClickOutside(event) {
    if (profileRef.current && !profileRef.current.contains(event.target)) {
      setProfileOpen(false);
    }
  }

  document.addEventListener("mousedown", handleClickOutside);
  return () => document.removeEventListener("mousedown", handleClickOutside);
}, []);

async function loadEvents() {
setLoading(true);
setError("");


try {
  const params = new URLSearchParams({ year: String(year) });
  if (filterType) params.set("event_type", filterType);

  const url = API + "?" + params.toString();
  const response = await fetch(url);


  if (!response.ok) {
    throw new Error(`Could not load events (${response.status}).`);
  }

  const data = await response.json();
  setEvents(data.events || []);
} catch (err) {
  setError(`${err.message} Check that the backend is running.`);
} finally {
  setLoading(false);
}

}

async function loadTypes() {
try {
const response = await fetch(`${API}/types`);

  if (!response.ok) {
    throw new Error("Could not load event types.");
  }

  const data = await response.json();
  const availableTypes = Array.isArray(data)
    ? data
    : data.types || [];

  setTypes(availableTypes);

  if (availableTypes.length > 0) {
    setForm((previous) => ({
      ...previous,
      event_type: previous.event_type || availableTypes[0],
    }));
  }
} catch (err) {
  setError(err.message);
}

}

useEffect(() => {
loadTypes();
}, []);

useEffect(() => {
loadEvents();
}, [year, filterType]);

function startEditing(event) {
setEditingId(event.event_id);
setForm({
name: event.name,
event_type: event.event_type,
start_date: event.start_date,
end_date: event.end_date,
});
}

function resetForm() {
setEditingId(null);
setForm({
...emptyForm,
event_type: types[0] || "",
});
}

async function saveEvent(event) {
event.preventDefault();
setSaving(true);
setError("");

try {
  const url = editingId ? `${API}/${editingId}` : API;

  const response = await fetch(url, {
    method: editingId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(form),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      data.detail || `Could not save event (${response.status}).`
    );
  }

  resetForm();
  await loadEvents();
} catch (err) {
  setError(err.message);
} finally {
  setSaving(false);
}

}

async function deleteEvent(eventId) {
if (!window.confirm("Delete this event?")) return;

setError("");

try {
  const response = await fetch(`${API}/${eventId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`Could not delete event (${response.status}).`);
  }

  if (editingId === eventId) resetForm();
  await loadEvents();
} catch (err) {
  setError(err.message);
}

}

return (
<div className="app-layout">
  <aside className="sidebar">
    <div className="brand">
      <span className="brand-name">Byte &amp; Bite</span>
      <img src={logo} alt="Byte & Bite" className="brand-logo" />
    </div>

    <div className="sidebar-section">
      <span className="sidebar-title">WORKSPACE</span>
      <nav>
        <a href="#dashboard" className="sidebar-link" onClick={(event) => {
          event.preventDefault();
          onDashboard();
        }}>
          <LayoutDashboard size={16} />
          Dashboard
        </a>
        <a href="#rush-hour-radar" className="sidebar-link" onClick={(event) => {
          event.preventDefault();
          onRushHourRadar();
        }}>
          <Clock3 size={16} />
          Rush Hour Radar
        </a>
        <a href="#demand-forecast" className="sidebar-link" onClick={(event) => {
          event.preventDefault();
          onDemandForecast();
        }}>
          <TrendingUp size={16} />
          Demand Forecast
        </a>
        <a href="#fair-comparison" className="sidebar-link" onClick={(event) => {
          event.preventDefault();
          onFairComparison();
        }}>
          <Scale size={16} />
          Fair Comparison
        </a>
        <a href="#context-events" className="sidebar-link active" aria-current="page">
          <CalendarDays size={16} />
          Calendar / Context Events
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
        Workspace / <strong>Calendar / Context Events</strong>
      </div>

      <div className="topbar-right">
        <button
          className="notification-button"
          onClick={() => (window.location.href = "/notifications")}
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
            aria-expanded={profileOpen}
          >
            <div className="user-avatar">{user.name.charAt(0)}</div>
            <div className="user-details">
              <strong>{user.name}</strong>
              <span>{user.role}</span>
            </div>
            <ChevronDown size={14} className="profile-chevron" />
          </button>

          {profileOpen && (
            <div className="profile-dropdown">
              <button
                className="logout-option"
                onClick={() => {
                  setProfileOpen(false);
                  onLogout();
                }}
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
      <div className="page-heading">
        <h1>Calendar &amp; Context Events</h1>
        <p>Manage academic dates and other events that influence student demand.</p>
      </div>

  {error && (
    <div
      role="alert"
      style={{
        padding: "12px",
        marginBottom: "18px",
        border: "1px solid #AC3E49",
        borderRadius: "8px",
        color: "#AC3E49",
      }}
    >
      {error}
      <button onClick={loadEvents} style={{ marginLeft: "12px" }}>
        <RefreshCw size={14} /> Retry
      </button>
    </div>
  )}

  <section
    className="panel"
    style={{ padding: "24px", marginBottom: "24px" }}
  >
    <h2>{editingId ? "Edit event" : "Add a context event"}</h2>

    <form
      onSubmit={saveEvent}
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "16px",
        alignItems: "end",
      }}
    >
      <label>
        Event name
        <input
          required
          value={form.name}
          onChange={(e) =>
            setForm({ ...form, name: e.target.value })
          }
          placeholder="e.g. Exam period"
        />
      </label>

      <label>
        Event type
        <select
          required
          value={form.event_type}
          onChange={(e) =>
            setForm({ ...form, event_type: e.target.value })
          }
        >
          <option value="">Choose type</option>
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>

      <label>
        Start date
        <input
          type="date"
          required
          value={form.start_date}
          onChange={(e) =>
            setForm({ ...form, start_date: e.target.value })
          }
        />
      </label>

      <label>
        End date
        <input
          type="date"
          required
          min={form.start_date || undefined}
          value={form.end_date}
          onChange={(e) =>
            setForm({ ...form, end_date: e.target.value })
          }
        />
      </label>

      <div style={{ display: "flex", gap: "8px" }}>
        <button
          className="btn-primary"
          type="submit"
          disabled={saving}
        >
          <Plus size={15} />{" "}
          {saving
            ? "Saving..."
            : editingId
              ? "Update event"
              : "Add event"}
        </button>

        {editingId && (
          <button
            className="btn-ghost"
            type="button"
            onClick={resetForm}
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  </section>

  <section className="panel" style={{ padding: "24px" }}>
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "12px",
        marginBottom: "20px",
      }}
    >
      <h2>Events</h2>

      <div style={{ display: "flex", gap: "10px" }}>
        <select
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
        >
          {[year - 1, year, year + 1].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All event types</option>
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
    </div>

    {loading ? (
      <p>Loading events...</p>
    ) : events.length === 0 ? (
      <p>No events found for these filters.</p>
    ) : (
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th align="left">Event</th>
              <th align="left">Type</th>
              <th align="left">Start</th>
              <th align="left">End</th>
              <th align="left">Actions</th>
            </tr>
          </thead>

          <tbody>
            {events.map((event) => (
              <tr key={event.event_id}>
                <td>{event.name}</td>
                <td>{event.event_type}</td>
                <td>{event.start_date}</td>
                <td>{event.end_date}</td>
                <td>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      className="btn-ghost"
                      onClick={() => startEditing(event)}
                    >
                      Edit
                    </button>

                    <button
                      className="btn-ghost"
                      onClick={() => deleteEvent(event.event_id)}
                      aria-label={`Delete ${event.name}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
</div>
</main>
</div>

);
}

export default ContextEvents;
