import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    AlertTriangle,
    Bell,
    CalendarDays,
    ChevronDown,
    Clock3,
    FileText,
    LayoutDashboard,
    LogOut,
    Scale,
    Search,
    TrendingUp,
    UserPlus,
    Users as UsersIcon,
} from "lucide-react";
import logo from "./assets/Logo.png";
import "./Users.css";
import { apiFetch, goToNotificationHistory } from "./api";
import ConfirmPopup from "./ConfirmPopup";


const EMPTY_FORM = { full_name: "", email: "", role: "Manager", vendor_ids: [] };

async function readError(response, fallback) {
    const data = await response.json().catch(() => ({}));
    return typeof data.detail === "string" ? data.detail : fallback;
}

function vendorSummary(person, vendorNames) {
    if (person.all_vendors) return "All vendors";
    const names = person.vendor_ids.map((id) => vendorNames[id] || `Vendor ${id}`);
    if (names.length === 0) return "—";
    if (names.length <= 2) return names.join(", ");
    return `${names.slice(0, 2).join(", ")} +${names.length - 2} more`;
}

// Staff are linked to exactly one vendor, Managers to one or more.
function VendorPicker({ vendors, role, selected, onChange }) {
    const [query, setQuery] = useState("");
    const single = role === "Staff";

    const shown = vendors.filter((vendor) =>
        (vendor.name || "").toLowerCase().includes(query.toLowerCase())
    );

    function toggle(id) {
        if (single) {
            onChange([id]);
        } else if (selected.includes(id)) {
            onChange(selected.filter((x) => x !== id));
        } else {
            onChange([...selected, id]);
        }
    }

    return (
        <div className="users-picker">
            <div className="users-picker-search">
                <Search size={15} />
                <input
                    type="search"
                    placeholder="Search vendors"
                    aria-label="Search vendors"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
            </div>

            <div className="users-picker-list">
                {shown.map((vendor) => (
                    <label key={vendor.vendor_id} className="users-picker-item">
                        <input
                            type={single ? "radio" : "checkbox"}
                            name="vendor-choice"
                            checked={selected.includes(vendor.vendor_id)}
                            onChange={() => toggle(vendor.vendor_id)}
                        />
                        {vendor.name}
                    </label>
                ))}
                {shown.length === 0 && <span>No vendors match.</span>}
            </div>

            <div className="users-picker-count">
                {single
                    ? "Staff can be linked to one vendor."
                    : `${selected.length} selected`}
            </div>
        </div>
    );
}

function Users({
    currentUser,
    onDashboard,
    onRushHourRadar,
    onDemandForecast,
    onFairComparison,
    onContextEvents,
    onLogout,
}) {
    const [users, setUsers] = useState([]);
    const [vendors, setVendors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [form, setForm] = useState(EMPTY_FORM);
    const [editingId, setEditingId] = useState(null);
    const [profileOpen, setProfileOpen] = useState(false);
    const profileRef = useRef(null);
    const [confirmPopup, setConfirmPopup] = useState(null);
    const [confirmLoading, setConfirmLoading] = useState(false);

    const me = currentUser || { name: "", role: "" };

    const vendorNames = useMemo(
        () => Object.fromEntries(vendors.map((v) => [v.vendor_id, v.name])),
        [vendors]
    );
    const lockedUsers = users.filter((person) => person.locked);

    useEffect(() => {
        function handleClickOutside(event) {
            if (profileRef.current && !profileRef.current.contains(event.target)) {
                setProfileOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const loadAll = useCallback(async () => {
        setLoading(true);
        try {
            const [usersResponse, vendorsResponse] = await Promise.all([
                apiFetch("/users"),
                apiFetch("/vendors"),
            ]);
            if (!usersResponse.ok) {
                throw new Error(await readError(usersResponse, "Could not load users."));
            }
            if (!vendorsResponse.ok) {
                throw new Error(await readError(vendorsResponse, "Could not load vendors."));
            }
            setUsers(await usersResponse.json());
            setVendors(await vendorsResponse.json());
        } catch (err) {
            setError(err.message || "Could not load the user list.");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadAll();
    }, [loadAll]);

    // Pick up new lockouts while the page stays open (UC-06).
    useEffect(() => {
        const timer = setInterval(async () => {
            try {
                const response = await apiFetch("/users");
                if (response.ok) setUsers(await response.json());
            } catch {
                /* ignore; the next tick tries again */
            }
        }, 30000);
        return () => clearInterval(timer);
    }, []);

    function resetForm() {
        setEditingId(null);
        setForm(EMPTY_FORM);
    }

    function startEditing(person) {
        setError("");
        setNotice("");
        setEditingId(person.user_id);
        setForm({
            full_name: person.full_name || "",
            email: person.email,
            role: person.role,
            vendor_ids: person.vendor_ids,
        });
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function changeRole(role) {
        setForm((previous) => ({
            ...previous,
            role,
            vendor_ids: role === "Staff" ? previous.vendor_ids.slice(0, 1) : previous.vendor_ids,
        }));
    }

    async function handleSubmit(event) {
        event.preventDefault();
        setError("");
        setNotice("");

        if (form.vendor_ids.length === 0) {
            setError("Choose at least one vendor.");
            return;
        }
        if (form.role === "Staff" && form.vendor_ids.length !== 1) {
            setError("Staff must be linked to exactly one vendor.");
            return;
        }

        setSaving(true);
        try {
            const isEdit = editingId !== null;
            const response = await apiFetch(
                isEdit ? `/users/${editingId}` : "/users/invite",
                {
                    method: isEdit ? "PATCH" : "POST",
                    body: JSON.stringify(
                        isEdit
                            ? {
                                full_name: form.full_name,
                                role: form.role,
                                vendor_ids: form.vendor_ids,
                            }
                            : form
                    ),
                }
            );
            if (!response.ok) {
                throw new Error(
                    await readError(response, "Please check the details and try again.")
                );
            }
            setNotice(isEdit ? "User updated." : `Invite sent to ${form.email}.`);
            resetForm();
            await loadAll();
        } catch (err) {
            setError(err.message || "Something went wrong. Please try again.");
        } finally {
            setSaving(false);
        }
    }

    async function runAction(path, method, fallbackMessage) {
        setError("");
        setNotice("");
        try {
            const response = await apiFetch(path, { method });
            if (!response.ok) {
                throw new Error(await readError(response, "That did not work. Please try again."));
            }
            const data =
                response.status === 204 ? null : await response.json().catch(() => null);
            setNotice(data?.message || fallbackMessage);
            await loadAll();
        } catch (err) {
            setError(err.message || "Something went wrong. Please try again.");
        }
    }

    function deactivate(person) {
       setConfirmPopup({
        title: "Deactivate Account",
        message: `Are you sure you want to deactivate ${person.email}? This user will no longer be able to access the system.`,
        confirmText: "Deactivate",
        variant: "danger",
        path: `/users/${person.user_id}/revoke`,
        method: "POST",
        successMessage: "Account Deactivated.",
    });
}

    function reactivate(person) {
        setConfirmPopup({
        title: "Reactivate Account",
        message: `Are you sure you want to reactivate ${person.email}? This user will regain access to the system.`,
        confirmText: "Reactivate",
        variant: "success",
        path: `/users/${person.user_id}/reactivate`,
        method: "POST",
        successMessage: "Account Reactivated.",
    });
}


    function sendReset(person) {
        runAction(`/users/${person.user_id}/reset-password`, "POST", "Password reset email sent.");
    }

    function resendInvite(person) {
        runAction(`/users/${person.user_id}/resend-invite`, "POST", "Invite re-sent.");
    }

    function remove(person) {
         setConfirmPopup({
        title: "Remove Account",
        message: `Are you sure you want to permanently remove ${person.email}? This action cannot be undone.`,
        confirmText: "Remove Permanently",
        variant: "danger",
        path: `/users/${person.user_id}`,
        method: "DELETE",
        successMessage: "User removed.",
        userId: person.user_id,
    });
}

    async function handleConfirm() {
    if (!confirmPopup || confirmLoading) return;

    setConfirmLoading(true);
    setError("");
    setNotice("");

    try {
        const response = await apiFetch(confirmPopup.path, {
            method: confirmPopup.method,
        });

        if (!response.ok) {
            throw new Error(
                await readError(response, "That did not work. Please try again.")
            );
        }

        const data =
            response.status === 204
                ? null
                : await response.json().catch(() => null);

        if (confirmPopup.userId === editingId) {
            resetForm();
        }

        setNotice(data?.message || confirmPopup.successMessage);
        setConfirmPopup(null);

        await loadAll();
    } catch (err) {
        setError(err.message || "Something went wrong. Please try again.");
    } finally {
        setConfirmLoading(false);
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
                        <a
                            href="#dashboard"
                            className="sidebar-link"
                            onClick={(event) => {
                                event.preventDefault();
                                onDashboard();
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
                                onRushHourRadar();
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
                                onDemandForecast();
                            }}
                        >
                            <TrendingUp size={16} />
                            Demand Forecast
                        </a>
                        <a
                            href="#fair-comparison"
                            className="sidebar-link"
                            onClick={(event) => {
                                event.preventDefault();
                                onFairComparison();
                            }}
                        >
                            <Scale size={16} />
                            Fair Comparison
                        </a>
                        <a
                            href="#context-events"
                            className="sidebar-link"
                            onClick={(event) => {
                                event.preventDefault();
                                onContextEvents();
                            }}
                        >
                            <CalendarDays size={16} />
                            Calendar / Context Events
                        </a>
                        <a
                            href="#users"
                            className="sidebar-link active"
                            aria-current="page"
                            onClick={(event) => event.preventDefault()}
                        >
                            <UsersIcon size={16} />
                            Users
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
                        Workspace / <strong>Users</strong>
                    </div>

                    <div className="topbar-right">
                        <button
                            className="notification-button"
                            onClick={goToNotificationHistory}
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
                                <div className="user-avatar">{(me.name || "?").charAt(0)}</div>
                                <div className="user-details">
                                    <strong>{me.name}</strong>
                                    <span>{me.role}</span>
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
                        <h1>Users</h1>
                        <p>Invite people and manage who can see which vendors.</p>
                    </div>

                    {error && (
                        <div className="users-banner error" role="alert">
                            {error}
                        </div>
                    )}
                    {notice && (
                        <div className="users-banner success" role="status">
                            {notice}
                        </div>
                    )}

                    {lockedUsers.length > 0 && (
                        <section className="users-locked" role="alert">
                            <h2>
                                <AlertTriangle size={18} />
                                Locked accounts need your attention
                            </h2>
                            <p>
                                These users failed to log in too many times. Send them a
                                password reset, or revoke their access.
                            </p>
                            {lockedUsers.map((person) => (
                                <div className="users-locked-row" key={person.user_id}>
                                    <div>
                                        <strong>{person.full_name || person.email}</strong>
                                        <div className="users-email">{person.email}</div>
                                    </div>
                                    <div className="users-locked-actions">
                                        <button
                                            className="btn-primary"
                                            onClick={() => sendReset(person)}
                                        >
                                            Send password reset
                                        </button>
                                        <button className="btn-ghost" onClick={() => revoke(person)}>
                                            Deactivate Account
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </section>
                    )}

                    <section className="panel users-panel">
                        <h2>{editingId !== null ? "Edit user" : "Invite a user"}</h2>
                        <p className="users-help">
                            {editingId !== null
                                ? "Change this user's name, role or linked vendors."
                                : "They will get an email with a link, valid for 24 hours, to set their own password."}
                        </p>

                        <form onSubmit={handleSubmit}>
                            <div className="users-form-grid">
                                <label className="users-field">
                                    Full name
                                    <input
                                        required
                                        value={form.full_name}
                                        onChange={(e) =>
                                            setForm({ ...form, full_name: e.target.value })
                                        }
                                        placeholder="e.g. Sam Jacobs"
                                    />
                                </label>

                                <label className="users-field">
                                    Email address
                                    <input
                                        type="email"
                                        required
                                        value={form.email}
                                        onChange={(e) =>
                                            setForm({ ...form, email: e.target.value })
                                        }
                                        disabled={editingId !== null}
                                        placeholder="name@example.com"
                                    />
                                </label>

                                <label className="users-field">
                                    Role
                                    <select
                                        value={form.role}
                                        onChange={(e) => changeRole(e.target.value)}
                                    >
                                        <option value="Manager">Manager</option>
                                        <option value="Staff">Staff</option>
                                    </select>
                                </label>

                                <div className="users-field users-field-wide">
                                    Vendors
                                    <VendorPicker
                                        vendors={vendors}
                                        role={form.role}
                                        selected={form.vendor_ids}
                                        onChange={(ids) => setForm({ ...form, vendor_ids: ids })}
                                    />
                                </div>
                            </div>

                            <div className="users-form-actions">
                                <button className="btn-primary" type="submit" disabled={saving}>
                                    <UserPlus size={15} />{" "}
                                    {saving
                                        ? "Saving..."
                                        : editingId !== null
                                            ? "Save changes"
                                            : "Send invite"}
                                </button>
                                {editingId !== null && (
                                    <button className="btn-ghost" type="button" onClick={resetForm}>
                                        Cancel
                                    </button>
                                )}
                            </div>
                        </form>
                    </section>

                    <section className="panel users-panel">
                        <h2>All users</h2>

                        {loading ? (
                            <div role="status" aria-label="Loading users" aria-busy="true">
                                <div aria-hidden="true">
                                    {[0, 1, 2, 3, 4].map((row) => (
                                        <div
                                            className="skeleton"
                                            key={row}
                                            style={{ height: 52, marginBottom: 10 }}
                                        />
                                    ))}
                                </div>
                            </div>
                        ) : users.length === 0 ? (
                            <p>No users yet.</p>
                        ) : (
                            <div className="users-table-wrap">
                                <table className="users-table">
                                    <thead>
                                        <tr>
                                            <th>User</th>
                                            <th>Role</th>
                                            <th>Vendors</th>
                                            <th>Status</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {users.map((person) => (
                                            <tr key={person.user_id}>
                                                <td>
                                                    <div className="users-name">
                                                        {person.full_name || "—"}
                                                    </div>
                                                    <div className="users-email">{person.email}</div>
                                                </td>
                                                <td>{person.role}</td>
                                                <td>{vendorSummary(person, vendorNames)}</td>
                                                <td>
                                                    <span className={`users-badge ${person.status}`}>
                                                        {person.status === "revoked"
                                                         ? "Deactivated"
                                                        : person.status}
                                                    </span>
                                                    {person.locked && (
                                                        <span className="users-badge locked">locked</span>
                                                    )}
                                                </td>
                                                <td>
                                                    {person.role === "Admin" ? (
                                                        "—"
                                                    ) : (
                                                        <div className="users-row-actions">
                                                            {person.status !== "revoked" && (
                                                                <button
                                                                    className="btn-ghost"
                                                                    onClick={() => startEditing(person)}
                                                                >
                                                                    Edit
                                                                </button>
                                                            )}
                                                            {person.status === "invited" && (
                                                                <button
                                                                    className="btn-ghost"
                                                                    onClick={() => resendInvite(person)}
                                                                >
                                                                    Resend invite
                                                                </button>
                                                            )}
                                                            {person.status === "active" && (
                                                                <button
                                                                    className="btn-ghost"
                                                                    onClick={() => sendReset(person)}
                                                                >
                                                                    Reset password
                                                                </button>
                                                            )}
                                                            {person.status !== "revoked" && (
                                                                <button
                                                                    className="btn-ghost"
                                                                    onClick={() => deactivate(person)}
                                                                >
                                                                    Deactivate
                                                                </button>
                                                            )}
                                                            
                                                             {person.status === "revoked" && (
                                                                 <button
                                                                    className="btn-primary"
                                                                    onClick={() => reactivate(person)}
                                                                     >
                                                                    Reactivate
                                                                        </button>
                                                                    )}

                                                            <button
                                                                className="btn-ghost"
                                                                onClick={() => remove(person)}
                                                            >
                                                                Remove
                                                            </button>
                                                        </div>
                                                    )}
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
            <ConfirmPopup
                open={confirmPopup !== null}
                title={confirmPopup?.title}
                message={confirmPopup?.message}
                confirmText={confirmPopup?.confirmText}
                variant={confirmPopup?.variant}
                loading={confirmLoading}
                onConfirm={handleConfirm}
                onCancel={() => {
                    if (!confirmLoading) setConfirmPopup(null);
                }}
            />
        </div>
    );
}

export default Users;