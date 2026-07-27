import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clearToken, getStoredEmail, getToken, setToken } from "../utils/auth";
import "../styles/portal.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState(getStoredEmail());
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (getToken()) navigate("/dashboard");
  }, []);

  const title = useMemo(
    () => (mode === "login" ? "Sign in to your account" : "Create an account"),
    [mode],
  );

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setStatus(mode === "login" ? "Signing in..." : "Creating account...");

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setStatus("Error: Please enter a valid email address");
      setBusy(false);
      return;
    }
    if (password.length < 6) {
      setStatus("Error: Password must be at least 6 characters");
      setBusy(false);
      return;
    }
    if (mode === "signup" && !name.trim()) {
      setStatus("Error: Name is required");
      setBusy(false);
      return;
    }

    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/signup";
      const payload = mode === "login"
        ? { email, password }
        : { email, name, password };

      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.message || "Authentication failed");
      }

      setToken(data.access_token, email);
      setStatus("Signed in successfully.");
      navigate("/dashboard");
    } catch (error) {
      clearToken();
      setStatus(`Error: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell">

      <section className="hero-card" style={{ marginBottom: 20 }}>
        <div className="eyebrow">Account access</div>
        <h1>{title}</h1>
        <p className="hero-copy">
          Use one account to manage batches and review submissions. Student uploads stay simple: roll number, access code, and file.
        </p>
      </section>

      <div className="dashboard-layout">
        <section className="form-card">
          <div className="section-label">{mode === "login" ? "Sign in" : "Create account"}</div>
          <h2 className="section-title">{mode === "login" ? "Welcome back" : "Set up your account"}</h2>
          <form onSubmit={handleSubmit} className="form-grid" style={{ marginTop: 20 }}>
            <div className="field">
              <label>Email</label>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@example.com"
                autoComplete="email"
              />
            </div>

            {mode === "signup" && (
              <div className="field">
                <label>Name</label>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Your name"
                  autoComplete="name"
                />
              </div>
            )}

            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
              <div className="field-help">
                Tokens are stored in localStorage on this device.
              </div>
            </div>

            <div className="toolbar">
              <button type="submit" className="button" disabled={busy}>
                {busy ? (mode === "login" ? "Signing in..." : "Creating...") : (mode === "login" ? "Sign in" : "Create account")}
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => setMode(mode === "login" ? "signup" : "login")}
                disabled={busy}
              >
                {mode === "login" ? "Need an account?" : "Already have an account?"}
              </button>
            </div>
          </form>

          <div className={`status-box ${status.startsWith("Error") ? "error" : status ? "success" : ""}`} style={{ marginTop: 18 }}>
            <strong>Status:</strong> {status || "Ready"}
          </div>
        </section>

        <aside className="guide-card">
          <div className="section-label">What this unlocks</div>
          <h2 className="section-title">General account flow</h2>
          <ul className="instruction-list" style={{ marginTop: 18 }}>
            <li>
              <span className="instruction-icon">1</span>
              <div>
                <strong>Create assignments</strong>
                <span>Signed-in users can create batches and access codes.</span>
              </div>
            </li>
            <li>
              <span className="instruction-icon">2</span>
              <div>
                <strong>Monitor progress</strong>
                <span>Live websocket updates still drive the matrix and progress bar.</span>
              </div>
            </li>
            <li>
              <span className="instruction-icon">3</span>
              <div>
                <strong>Keep student uploads simple</strong>
                <span>Students only need the access code and file unless they want to store name or email.</span>
              </div>
            </li>
          </ul>
        </aside>
      </div>
    </div>
  );
}