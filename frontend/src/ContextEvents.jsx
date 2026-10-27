import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bell,
  CalendarDays,
  ChevronDown,
  LogOut,
  Plus,
  RefreshCw,
  Trash2,
  ChevronLeft,
  ChevronRight,
  List,
  X,
} from "lucide-react";
import { apiFetch } from "./api";
import WorkspaceSidebar from "./WorkspaceSidebar";
import UsersLink from "./UsersLink";
import ReportButton from "./ReportButton";

const API = "/context-events";
const CALENDAR_MODES = ["month", "week", "day"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateKey(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

function addDays(date, amount) {
  const result = new Date(date);
  result.setDate(result.getDate() + amount);
  return result;
}

function startOfWeek(date) {
  const result = new Date(date);
  result.setDate(result.getDate() - ((result.getDay() + 6) % 7));
  result.setHours(12, 0, 0, 0);
  return result;
}

function formatCalendarDate(date, options = { month: "long", year: "numeric" }) {
  return date.toLocaleDateString("en-ZA", options);
}

function isEventOnDate(event, date) {
  const key = dateKey(date);
  return event.start_date <= key && event.end_date >= key;
}

function eventTypeColor(type, types) {
  const index = Math.max(0, types.indexOf(type)) % 8;
  return `event-type-color-${index}`;
}

function ContextEvents({
  currentUser,
  onNavigate,
  onLogout,
}) {
const [events, setEvents] = useState([]);
const [types, setTypes] = useState([]);
const [year, setYear] = useState(null);
const displayYear = year ?? new Date().getFullYear();
const [filterType, setFilterType] = useState("");
const [loading, setLoading] = useState(true);
const [saving, setSaving] = useState(false);
const [error, setError] = useState("");
const [editingId, setEditingId] = useState(null);
const [profileOpen, setProfileOpen] = useState(false);
const [displayMode, setDisplayMode] = useState("list");
const [calendarMode, setCalendarMode] = useState("month");
const [calendarDate, setCalendarDate] = useState(() => new Date());
const [selectedEvent, setSelectedEvent] = useState(null);
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

const loadEvents = useCallback(async (signal) => {
setLoading(true);
setError("");


try {
  const params = new URLSearchParams();
  if (year) params.set("year", String(year));
  if (filterType) params.set("event_type", filterType);

  const query = params.toString();
  const url = query ? `${API}?${query}` : API;
  const response = await apiFetch(url, signal ? { signal } : {});


  if (!response.ok) {
    throw new Error(`Could not load events (${response.status}).`);
  }

  const data = await response.json();
  const loadedEvents = data.events || [];
  setEvents(loadedEvents);
  if (!year) {
    const latestEvent = loadedEvents.reduce((latest, event) => {
      if (!latest || event.start_date > latest.start_date) return event;
      return latest;
    }, null);
    const latestEventYear = latestEvent ? Number(latestEvent.start_date.slice(0, 4)) : 0;
    if (latestEvent) setCalendarDate(parseDateKey(latestEvent.start_date));
    setYear(latestEventYear || new Date().getFullYear());
  }
} catch (err) {
  if (err.name !== "AbortError") {
    setError(`${err.message} Check that the backend is running.`);
  }
} finally {
  if (!signal?.aborted) setLoading(false);
}

}, [year, filterType]);

const loadTypes = useCallback(async () => {
try {
const response = await apiFetch(`${API}/types`);

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

}, []);

useEffect(() => {
  const timer = window.setTimeout(() => void loadTypes(), 0);
  return () => window.clearTimeout(timer);
}, [loadTypes]);

useEffect(() => {
  const controller = new AbortController();
  const timer = window.setTimeout(() => void loadEvents(controller.signal), 0);
  return () => {
    window.clearTimeout(timer);
    controller.abort();
  };
}, [loadEvents]);

const monthStart = new Date(calendarDate.getFullYear(), calendarDate.getMonth(), 1, 12);
const calendarDays = calendarMode === "month"
  ? Array.from({ length: 42 }, (_, index) =>
      addDays(startOfWeek(monthStart), index)
    )
  : calendarMode === "week"
    ? Array.from({ length: 7 }, (_, index) =>
        addDays(startOfWeek(calendarDate), index)
      )
    : [new Date(calendarDate)];

function navigateCalendar(direction) {
  const nextDate = new Date(calendarDate);
  if (calendarMode === "month") {
    nextDate.setDate(1);
    nextDate.setMonth(nextDate.getMonth() + direction);
  } else {
    nextDate.setDate(nextDate.getDate() + direction * (calendarMode === "week" ? 7 : 1));
  }
  nextDate.setHours(12, 0, 0, 0);
  setCalendarDate(nextDate);
  setYear(nextDate.getFullYear());
}

function goToToday() {
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  setCalendarDate(today);
  setYear(today.getFullYear());
}

function selectYear(nextYear) {
  const numericYear = Number(nextYear);
  setYear(numericYear);
  setCalendarDate((current) => {
    const day = current.getDate();
    const next = new Date(numericYear, current.getMonth(), 1, 12);
    next.setDate(Math.min(day, new Date(numericYear, current.getMonth() + 1, 0).getDate()));
    return next;
  });
}

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

  const response = await apiFetch(url, {
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
  const response = await apiFetch(`${API}/${eventId}`, {
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
  <WorkspaceSidebar activeView="context" onNavigate={onNavigate} />

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
      <div className="demand-page-header report-heading">
        <div className="page-heading">
          <h1>Calendar &amp; Context Events</h1>
          <p>Manage academic dates and other events that influence student demand.</p>
        </div>

        {!loading && events.length > 0 && (
          <ReportButton
            title="Calendar / Context Events"
            subtitle={`${displayYear} · ${filterType || "All event types"}`}
            reportType="calendar_events"
            periodStart={`${displayYear}-01-01`}
            periodEnd={`${displayYear}-12-31`}
          />
        )}
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
    className="panel no-print"
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

  <section className="panel context-events-panel">
    <div className="context-events-toolbar">
      <h2>Events</h2>
      <div className="context-events-controls">
        <label>
          Year
          <select
            value={displayYear}
            onChange={(e) => {
              setSelectedEvent(null);
              selectYear(e.target.value);
            }}
          >
            {[displayYear - 1, displayYear, displayYear + 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </label>
        <label>
          Event type
          <select
            value={filterType}
            onChange={(e) => {
              setSelectedEvent(null);
              setFilterType(e.target.value);
            }}
          >
            <option value="">All event types</option>
            {types.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </label>
        <div className="context-view-switch" role="group" aria-label="Events view">
          <button
            type="button"
            className={displayMode === "list" ? "selected" : ""}
            aria-pressed={displayMode === "list"}
            onClick={() => setDisplayMode("list")}
          >
            <List size={16} /> List
          </button>
          <button
            type="button"
            className={displayMode === "calendar" ? "selected" : ""}
            aria-pressed={displayMode === "calendar"}
            onClick={() => setDisplayMode("calendar")}
          >
            <CalendarDays size={16} /> Calendar
          </button>
        </div>
      </div>
    </div>

    {displayMode === "calendar" && (
      <>
        <div className="context-calendar-toolbar">
          <div className="context-calendar-navigation">
            <button type="button" className="btn-ghost" onClick={() => navigateCalendar(-1)} aria-label="Previous period">
              <ChevronLeft size={17} />
            </button>
            <button type="button" className="btn-ghost" onClick={goToToday}>Today</button>
            <button type="button" className="btn-ghost" onClick={() => navigateCalendar(1)} aria-label="Next period">
              <ChevronRight size={17} />
            </button>
            <h3>
              {calendarMode === "month"
                ? formatCalendarDate(calendarDate)
                : calendarMode === "week"
                  ? `${formatCalendarDate(calendarDays[0], { day: "numeric", month: "short" })} – ${formatCalendarDate(calendarDays[6], { day: "numeric", month: "short", year: "numeric" })}`
                  : formatCalendarDate(calendarDate, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </h3>
          </div>
          <div className="context-calendar-mode" role="group" aria-label="Calendar display period">
            {CALENDAR_MODES.map((mode) => (
              <button
                type="button"
                key={mode}
                className={calendarMode === mode ? "selected" : ""}
                aria-pressed={calendarMode === mode}
                onClick={() => setCalendarMode(mode)}
              >
                {mode[0].toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="context-calendar-legend" aria-label="Event type legend">
          {types.map((type) => (
            <span key={type}>
              <i className={`context-event-dot ${eventTypeColor(type, types)}`} />
              {type}
            </span>
          ))}
        </div>

        {loading ? (
          <div className="context-events-state" role="status">Loading calendar events…</div>
        ) : error ? null : events.length === 0 ? (
          <div className="context-events-state" role="status">No events found for these filters.</div>
        ) : (
          <div className={`context-calendar context-calendar-${calendarMode}`}>
            {calendarMode === "month" && (
              <div className="context-calendar-weekdays" aria-hidden="true">
                {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
              </div>
            )}
            <div className="context-calendar-grid">
              {calendarDays.map((day) => {
                const key = dateKey(day);
                const dayEvents = events.filter((event) => isEventOnDate(event, day));
                const isCurrentMonth = day.getMonth() === calendarDate.getMonth();
                const isToday = key === dateKey(new Date());
                return (
                  <section
                    key={key}
                    className={[
                      "context-calendar-day",
                      !isCurrentMonth && calendarMode === "month" ? "outside-month" : "",
                      isToday ? "today" : "",
                    ].filter(Boolean).join(" ")}
                    aria-label={formatCalendarDate(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                  >
                    {calendarMode !== "month" && (
                      <div className="context-calendar-day-heading">
                        <span>{formatCalendarDate(day, { weekday: "short" })}</span>
                        <strong>{formatCalendarDate(day, { day: "numeric", month: "short" })}</strong>
                      </div>
                    )}
                    {calendarMode === "month" && (
                      <span className="context-calendar-day-number">{day.getDate()}</span>
                    )}
                    <div className="context-calendar-day-events">
                      {dayEvents.map((event) => (
                        <button
                          type="button"
                          key={event.event_id}
                          className={`context-calendar-event ${eventTypeColor(event.event_type, types)}${selectedEvent?.event_id === event.event_id ? " selected" : ""}`}
                          title={`${event.name} — ${event.event_type}`}
                          onClick={() => setSelectedEvent(event)}
                        >
                          <strong>{event.name}</strong>
                          <span>{event.event_type}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
        )}

        {selectedEvent && (
          <section className="context-event-details" aria-live="polite">
            <div className="context-event-details-heading">
              <div>
                <span className={`context-event-type-pill ${eventTypeColor(selectedEvent.event_type, types)}`}>
                  {selectedEvent.event_type}
                </span>
                <h3>{selectedEvent.name}</h3>
              </div>
              <button type="button" className="btn-ghost" aria-label="Close event details" onClick={() => setSelectedEvent(null)}>
                <X size={17} />
              </button>
            </div>
            <dl>
              <div><dt>Date</dt><dd>{formatCalendarDate(parseDateKey(selectedEvent.start_date), { day: "numeric", month: "long", year: "numeric" })}{selectedEvent.end_date !== selectedEvent.start_date && ` – ${formatCalendarDate(parseDateKey(selectedEvent.end_date), { day: "numeric", month: "long", year: "numeric" })}`}</dd></div>
              {(selectedEvent.start_time || selectedEvent.end_time || selectedEvent.all_day) && (
                <div><dt>Time</dt><dd>{selectedEvent.all_day ? "All day" : [selectedEvent.start_time, selectedEvent.end_time].filter(Boolean).join(" – ")}</dd></div>
              )}
              {selectedEvent.notes && <div><dt>Description / notes</dt><dd>{selectedEvent.notes}</dd></div>}
              {["subcategory", "location", "campus", "faculty", "scope", "verification_status"].map((field) =>
                selectedEvent[field] ? <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{selectedEvent[field]}</dd></div> : null
              )}
              {["source", "source_organisation", "source_name", "source_file", "source_url", "source_page"].map((field) =>
                selectedEvent[field] ? <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{field === "source_url" ? <a href={selectedEvent[field]} target="_blank" rel="noreferrer">{selectedEvent[field]}</a> : selectedEvent[field]}</dd></div> : null
              )}
            </dl>
          </section>
        )}
      </>
    )}

    {displayMode === "list" && (
      loading ? (
        <div className="context-events-state" role="status">Loading events…</div>
      ) : error ? null : events.length === 0 ? (
        <div className="context-events-state" role="status">No events found for these filters.</div>
      ) : (
        <div className="context-events-table-wrap">
          <table className="context-events-table">
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
                  <td>
                    <button type="button" className="context-event-list-name" onClick={() => setSelectedEvent(event)}>{event.name}</button>
                  </td>
                  <td>{event.event_type}</td>
                  <td>{event.start_date}</td>
                  <td>{event.end_date}</td>
                  <td>
                    <div className="context-event-actions">
                      <button className="btn-ghost" onClick={() => startEditing(event)}>Edit</button>
                      <button className="btn-ghost" onClick={() => deleteEvent(event.event_id)} aria-label={`Delete ${event.name}`}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    )}
  </section>

  {displayMode === "list" && selectedEvent && (
    <section className="context-event-details" aria-live="polite">
      <div className="context-event-details-heading">
        <div>
          <span className={`context-event-type-pill ${eventTypeColor(selectedEvent.event_type, types)}`}>{selectedEvent.event_type}</span>
          <h3>{selectedEvent.name}</h3>
        </div>
        <button type="button" className="btn-ghost" aria-label="Close event details" onClick={() => setSelectedEvent(null)}><X size={17} /></button>
      </div>
      <dl>
        <div><dt>Date</dt><dd>{selectedEvent.start_date}{selectedEvent.end_date !== selectedEvent.start_date && ` – ${selectedEvent.end_date}`}</dd></div>
        {(selectedEvent.start_time || selectedEvent.end_time || selectedEvent.all_day) && (
          <div><dt>Time</dt><dd>{selectedEvent.all_day ? "All day" : [selectedEvent.start_time, selectedEvent.end_time].filter(Boolean).join(" – ")}</dd></div>
        )}
        {selectedEvent.notes && <div><dt>Description / notes</dt><dd>{selectedEvent.notes}</dd></div>}
        {["subcategory", "location", "campus", "faculty", "scope", "verification_status", "source", "source_organisation", "source_name", "source_file", "source_url", "source_page"].map((field) =>
          selectedEvent[field] ? <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{field === "source_url" ? <a href={selectedEvent[field]} target="_blank" rel="noreferrer">{selectedEvent[field]}</a> : selectedEvent[field]}</dd></div> : null
        )}
      </dl>
    </section>
  )}
</div>
</main>
</div>

);
}

export default ContextEvents;
