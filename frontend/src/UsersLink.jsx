import { Users } from "lucide-react";
import { getStoredUser } from "./api";

// Menu item for the profile dropdown, shown to Admins only. App.jsx opens the
// Users page when the address changes to #users.
function UsersLink() {
    if (getStoredUser()?.role !== "Admin") return null;

    return (
        <button
            type="button"
            className="logout-option users-option"
            onClick={() => {
                window.location.hash = "#users";
            }}
        >
            <Users size={15} />
            Users
        </button>
    );
}

export default UsersLink;