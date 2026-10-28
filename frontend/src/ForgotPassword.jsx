import { useState } from "react";
import { Mail } from "lucide-react";
import logo from "./assets/Logo.png";
import "./Login.css";
import { apiFetch } from "./api";

// Opened from "Forgot password?" on the login page: /forgot-password
function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [sent, setSent] = useState(false);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError("");
        setLoading(true);
        try {
            const response = await apiFetch("/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email: email.trim() }),
            });
            if (!response.ok) {
                setError("Please enter a valid email address and try again.");
                return;
            }
            setSent(true);
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

                {sent ? (
                    <>
                        <div className="login-heading">
                            <h2>Check your email</h2>
                            <p className="login-success">
                                If an account exists for {email.trim()}, we have sent a link
                                to reset your password. It expires in 60 minutes. If you
                                cannot see it, check your spam folder.
                            </p>
                        </div>
                        <button
                            type="button"
                            className="login-button"
                            onClick={() => (window.location.href = "/")}
                        >
                            Back to log in
                        </button>
                        <div className="login-options">
                            <a
                                href="/forgot-password"
                                onClick={(event) => {
                                    event.preventDefault();
                                    setSent(false);
                                }}
                            >
                                Use a different email
                            </a>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="login-heading">
                            <h2>Forgot your password?</h2>
                            <p>Enter your email and we will send you a link to choose a new one.</p>
                        </div>

                        <form onSubmit={handleSubmit}>
                            <div className="login-field">
                                <label htmlFor="reset-email">Email address</label>
                                <div className="input-wrapper">
                                    <Mail size={17} />
                                    <input
                                        id="reset-email"
                                        type="email"
                                        placeholder="Enter your email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        autoComplete="email"
                                        disabled={loading}
                                        required
                                    />
                                </div>
                            </div>

                            {error && (
                                <p className="login-error" role="alert">
                                    {error}
                                </p>
                            )}

                            <button type="submit" className="login-button" disabled={loading}>
                                {loading ? "Sending..." : "Send reset link"}
                            </button>

                            <div className="login-options">
                                <a href="/">Back to log in</a>
                            </div>
                        </form>
                    </>
                )}

            </div>
        </div>
    );
}

export default ForgotPassword;