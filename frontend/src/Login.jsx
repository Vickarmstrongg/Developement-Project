import { useState } from "react";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";
import logo from "./assets/Logo.png";
import "./Login.css";

function Login({ onLogin }) {
    const [showPassword, setShowPassword] = useState(false);

    const handleSubmit = (event) => {
        event.preventDefault();
        //Temporary frontend Login. Real authentication will be connected to backend later.
        onLogin();
    };

    return (
        <div className="login-page">
            <div className="login-card">

                <div className="login-brand">
                    <img
                        src={logo}
                        alt="Byte & Bite"
                        className="login-logo"
                    />

                    <h1>Byte & Bite</h1>
                    <p>Business Intelligence Platform</p>
                </div>

                <div className="login-heading">
                    <h2>Welcome back</h2>
                    <p>Sign in to access your business dashboard</p>
                </div>

                <form onSubmit={handleSubmit}>

                    <div className="login-field">
                        <label htmlFor="email">Email address</label>

                        <div className="input-wrapper">
                            <Mail size={17} />

                            <input
                                id="email"
                                type="email"
                                placeholder="Enter your email"
                                required
                            />
                        </div>
                    </div>

                    <div className="login-field">
                        <label htmlFor="password">Password</label>

                        <div className="input-wrapper">
                            <Lock size={17} />

                            <input
                                id="password"
                                type={showPassword ? "text" : "password"}
                                placeholder="Enter your password"
                                required
                            />

                            <button
                                type="button"
                                className="password-toggle"
                                onClick={() => setShowPassword(!showPassword)}
                                aria-label={
                                    showPassword
                                        ? "Hide password"
                                        : "Show password"
                                }
                            >
                                {showPassword ? (
                                    <EyeOff size={17} />
                                ) : (
                                    <Eye size={17} />
                                )}
                            </button>
                        </div>
                    </div>

                    <div className="login-options">
                        <a href="forgot-password">
                            Forgot password?
                        </a>
                    </div>

                    <button type="submit" className="login-button">
                        Log In
                    </button>

                </form>

                <div className="login-footer">
                    <div className="footer-divider"></div>

                    <p>Access is invite-only - Ask your Admin for a new invite</p>
                </div>

            </div>
        </div>
    );
}

export default Login;