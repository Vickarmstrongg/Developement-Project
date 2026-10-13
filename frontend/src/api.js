// Talks to the Byte & Bite backend and remembers who is logged in.
// Set VITE_API_URL in frontend/.env to change the address (restart Vite after).
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "bb_token";
const USER_KEY = "bb_user";

export function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
    try {
        return JSON.parse(sessionStorage.getItem(USER_KEY));
    } catch {
        return null;
    }
}

export function saveSession(token, user) {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
}

// Use this instead of fetch() for every backend call after login.
// It adds the token and signs the user out if the server says it has expired.
export async function apiFetch(path, options = {}) {
    const token = getToken();
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
        },
    });
    if (response.status === 401 && token) {
        clearSession();
        window.dispatchEvent(new Event("bb-logout"));
    }
    return response;
}

// Calls POST /auth/login. Returns the user, or throws an Error whose message
// is safe to show on screen.
export async function login(email, password) {
    let response;
    try {
        response = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
    } catch {
        throw new Error("Cannot reach the server. Please try again shortly.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(
            typeof data.detail === "string"
                ? data.detail
                : "Login failed. Please try again."
        );
    }
    saveSession(data.access_token, data.user);
    return data.user;
}