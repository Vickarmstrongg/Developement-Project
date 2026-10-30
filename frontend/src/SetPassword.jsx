import { useState, useEffect } from "react";
import { Lock, Eye, EyeOff } from "lucide-react";
import logo from "./assets/Logo.png";
import "./Login.css";
import { apiFetch } from "./api";

// Opened from the invite / reset email: /set-password?token=...
function SetPassword() {
    
const [token,] = useState(
    () => new URLSearchParams(window.location.search).get("token") || ""
);

useEffect(() => {
    if(window.location.search) {
        window.history.replaceState(null, "", window.location.pathname);
        }
    }, []);


    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [done, setDone] = useState(false);


    const handleSubmit = async (event) => {
        event.preventDefault();
        setError("");
        

        if (password.length < 8) {
            setError("Password must be at least 8 characters long.");
            return;
        }
        if (password !== confirm) {
            setError("The two passwords do not match.");
            return;
        }

        setLoading(true);
        try {
            const response = await apiFetch("/auth/set-password", {
                method: "POST",
                body: JSON.stringify({ token: token.trim(), password }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                setError(
                    typeof data.detail === "string"
                        ? data.detail
                        : "Could not set your password. Please check it and try again."
                );
                return;
            }
            setDone(true);
        } catch {
            setError("Cannot reach the server. Please try again shortly.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-card">

                <div className="login-brand">
                    <img src={logo} alt="Byte & Bite" className="login-logo" />
                    <h1>Byte & Bite</h1>
                    <p>Business Intelligence Platform</p>
                </div>

            {/*
{!token ? (
                    <>
                        <div className="login-heading">
                            <h2>Open the link from your email</h2>
                            <p>This page can only be opened from the link in your invite or
                                reset email. Open that email and click the link again. If it
                                has expired, ask your Admin for a new invite.</p>
                        </div>
                        <button
                            type="button"
                            className="login-button"
                            onClick={() => (window.location.href = "/")}
                        >
                            Back to log in
                        </button>
                    </>
                    */}
                
                { done ? (
                    <>
                        <div className="login-heading">
                            <h2>Password set</h2>
                            <p className="login-success">Your account is ready. You can now log in.</p>
                        </div>
                        <button
                            type="button"
                            className="login-button"
                            onClick={() => (window.location.href = "/")}
                        >
                            Go to log in
                        </button>
                    </>
                ) : (
                    <>
                        <div className="login-heading">
                            <h2>Set your password</h2>
                            <p>Choose a password to activate your account</p>
                        </div>

                        <form onSubmit={handleSubmit}>
                            <div className="login-field"> 
                               
                                <label htmlFor="new-password">New password</label>
                                <div className="input-wrapper">
                                    <Lock size={17} />
                                    <input
                                        id="new-password"
                                        type={showPassword ? "text" : "password"}
                                        placeholder="At least 8 characters"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        autoComplete="new-password"
                                        disabled={loading}
                                        required
                                    />
                                     <button
                                        type="button"
                                        className="password-toggle"
                                        onClick={() => setShowPassword(!showPassword)}
                                        aria-label={showPassword ? "Hide password" : "Show password"}
                                        aria-pressed={showPassword}
                                        >
                                             {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                                             </button>
                                </div>
                            </div>

                            <div className="login-field">
                                <label htmlFor="confirm-password">Confirm password</label>
                                <div className="input-wrapper">
                                    <Lock size={17} />
                                    <input
                                        id="confirm-password"
                                        type={showConfirm ? "text" : "password"}
                                        placeholder="Repeat your password"
                                        value={confirm}
                                        onChange={(e) => setConfirm(e.target.value)}
                                        autoComplete="new-password"
                                        disabled={loading}
                                        required
                                    />
                                     <button
                                        type="button"
                                        className="password-toggle"
                                        onClick={() => setShowConfirm(!showConfirm)}
                                        aria-label={showConfirm ? "Hide password" : "Show password"}
                                        aria-pressed={showConfirm}
                                    >
                                        {showConfirm ? <EyeOff size={17} /> : <Eye size={17} />}
                                    </button>
                                </div>
                            </div>

                            {error && (
                                <p className="login-error" role="alert">
                                    {error}
                                </p>
                            )}

                            <button type="submit" className="login-button" disabled={loading}>
                                {loading ? "Saving..." : "Set password"}
                            </button>
                        </form>
                    </>
                )}

            </div>
        </div>
    );
}

export default SetPassword;