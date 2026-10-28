import { Users } from "lucide-react";
import { getStoredUser } from "./api";

// Sidebar tab, shown to Admins only. App.jsx opens the Users page when the
// address changes to #users.
function UsersLink() {
    if (getStoredUser()?.role !== "Admin") return null;

    return (
        <a href="#users" className="sidebar-link">
            <Users size={16} />
            Users
        </a>
    );
}

export default UsersLink;