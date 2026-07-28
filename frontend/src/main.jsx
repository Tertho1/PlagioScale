import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom'
import AuthPage from './pages/AuthPage'
import Dashboard from './pages/Dashboard'
import StudentSubmit from './pages/StudentSubmit'
import StudentDashboard from './pages/StudentDashboard'
import AdminPage from './pages/AdminPage'
import CrossBatchPage from './pages/CrossBatchPage'
import StudentComparison from './pages/StudentComparison'
import { clearToken, getStoredEmail, getToken } from './utils/auth'
import ToastContainer from './components/Toast'
import './index.css'
import './styles/portal.css'

const TOOLS = [
  { label: "Monitor", url: "http://localhost:8090", icon: "📊" },
  { label: "Grafana", url: "http://localhost:3000", icon: "📈" },
  { label: "Prometheus", url: "http://localhost:9090", icon: "📉" },
]

function NavBar(){
  const location = useLocation()
  const token = getToken()
  const email = getStoredEmail()
  const [showTools, setShowTools] = useState(false)
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <nav className="root-nav">
      <Link to="/" className="root-nav-home">PlagioScale</Link>
      <div className="root-nav-links">
        <Link to="/">Home</Link>
        <Link to="/student">Submit</Link>
        {token ? (
          <>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/student/dashboard">My Dashboard</Link>
            <Link to="/cross-batch">Cross-Batch</Link>
            <div style={{ position: "relative" }}>
              <button type="button" className="nav-link" onClick={() => setShowTools(!showTools)}>Tools</button>
              {showTools && (
                <div style={{ position: "absolute", top: "100%", left: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(0,0,0,0.12)", padding: 8, zIndex: 1000, display: "flex", flexDirection: "column", gap: 4, minWidth: 180 }}>
                  {TOOLS.map(t => (
                    <a key={t.label} href={t.url} target="_blank" rel="noopener noreferrer" style={{ padding: "8px 12px", borderRadius: 6, textDecoration: "none", color: "#1e293b", display: "flex", alignItems: "center", gap: 8, fontSize: 14 }} onMouseOver={e => e.target.style.background = "#f1f5f9"} onMouseOut={e => e.target.style.background = "transparent"}>
                      <span>{t.icon}</span> {t.label}
                    </a>
                  ))}
                </div>
              )}
            </div>
            <span className="nav-email">{email}</span>
            <button
              type="button"
              className="nav-link"
              onClick={() => setDark(!dark)}
              title="Toggle dark mode"
            >
              {dark ? '☀️' : '🌙'}
            </button>
            <button
              type="button"
              className="nav-link root-nav-logout"
              onClick={() => { clearToken(); window.location.href = '/' }}
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link to="/auth">Login / Sign up</Link>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/student/dashboard">My Dashboard</Link>
          </>
        )}
      </div>
    </nav>
  )
}

function Home(){
  const token = getToken()
  const email = getStoredEmail()

  return (
    <div className="home-shell">
      <section className="home-hero">
        <div className="home-hero-copy">
          <p className="hero-kicker">PlagioScale workspace</p>
          <h1>Assignments, review, and submissions in one shared workspace.</h1>
          <p className="hero-summary">
            {token
              ? `Signed in as ${email}. Manage assignments, review submissions, and drill into each batch.`
              : 'Sign in or create an account, then land on a dashboard where you can create assignments, review submissions, and drill into each assignment detail.'}
          </p>
          <div className="hero-actions">
            {token ? (
              <Link to="/dashboard" className="button hero-button-primary">Go to Dashboard</Link>
            ) : (
              <Link to="/auth" className="button hero-button-primary">Login / Sign up</Link>
            )}
            <Link to="/student" className="button-secondary hero-button-secondary">Submit an assignment</Link>
          </div>
        </div>
        <div className="home-hero-panel">
          <div className="hero-panel-card hero-panel-card-main">
            <span className="hero-panel-label">Workspace</span>
            <strong>One account. Multiple roles.</strong>
            <p>Any user can create assignments, explore details, and review submissions from the same dashboard.</p>
          </div>
          <div className="hero-panel-grid">
            <div className="hero-mini-card">
              <span>Login</span>
              <strong>General access</strong>
            </div>
            <div className="hero-mini-card">
              <span>Dashboard</span>
              <strong>Assignments + detail</strong>
            </div>
            <div className="hero-mini-card">
              <span>Submit</span>
              <strong>Roll + code + file</strong>
            </div>
            <div className="hero-mini-card">
              <span>Review</span>
              <strong>Similarity matrix</strong>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function Root(){
  return (
    <BrowserRouter>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="root-shell">
        <NavBar />
        <ToastContainer />
        <Routes>
          <Route path="/" element={<Home/>} />
          <Route path="/auth" element={<AuthPage/>} />
          <Route path="/dashboard" element={<Dashboard/>} />
          <Route path="/student" element={<StudentSubmit/>} />
          <Route path="/teacher" element={<Dashboard/>} />
          <Route path="/student/dashboard" element={<StudentDashboard/>} />
          <Route path="/admin" element={<AdminPage/>} />
          <Route path="/cross-batch" element={<CrossBatchPage/>} />
          <Route path="/student/comparison/:submissionId" element={<StudentComparison/>} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
