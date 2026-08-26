import React, { Suspense, useEffect, useRef, useState } from 'react'
import { Routes, Route, Link } from 'react-router-dom'
const AuthPage = React.lazy(() => import('./pages/AuthPage'))
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const StudentSubmit = React.lazy(() => import('./pages/StudentSubmit'))
const AdminPage = React.lazy(() => import('./pages/AdminPage'))
const CrossBatchPage = React.lazy(() => import('./pages/CrossBatchPage'))
const StudentComparison = React.lazy(() => import('./pages/StudentComparison'))
import { RequireAuth, RequireRole } from './components/AuthGuards'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import ToastContainer from './components/Toast'
import './index.css'
import './styles/portal.css'

const TOOLS = [
  { label: "Monitor", url: "http://localhost:8090", icon: "📊" },
  { label: "Grafana", url: "http://localhost:3000", icon: "📈" },
  { label: "Prometheus", url: "http://localhost:9090", icon: "📉" },
]

function NavBar(){
  const { token, email, logout } = useAuth();
  const [showTools, setShowTools] = useState(false)
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem('theme');
    if (stored) return stored === 'dark';
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  })
  const toolsRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    if (!showTools) return;
    const handleClickOutside = (e) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target)) setShowTools(false);
    };
    const handleEscape = (e) => {
      if (e.key === 'Escape') setShowTools(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [showTools]);

  return (
    <nav className="root-nav">
      <Link to="/" className="root-nav-home">PlagioScale</Link>
      <div className="root-nav-links">
        <Link to="/">Home</Link>
        <Link to="/student">Submit</Link>
        {token ? (
          <>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/cross-batch">Cross-Batch</Link>
            <div className="nav-tools" ref={toolsRef}>
              <button type="button" className="nav-link" onClick={() => setShowTools(!showTools)} aria-expanded={showTools} aria-haspopup="true">Tools</button>
              {showTools && (
                <div role="menu" className="nav-tools-menu">
                  {TOOLS.map(t => (
                    <a key={t.label} role="menuitem" className="nav-tools-item" href={t.url} target="_blank" rel="noopener noreferrer">
                      <span aria-hidden="true">{t.icon}</span> {t.label}
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
              onClick={() => { logout(); window.location.href = '/' }}
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link to="/auth">Login / Sign up</Link>
          </>
        )}
      </div>
    </nav>
  )
}

function Home(){
  const { token, email } = useAuth();

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

export default function App() {
  return (
    <AuthProvider>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="root-shell">
        <NavBar />
        <ToastContainer />
        <ErrorBoundary>
        <Suspense fallback={<div style={{ padding: 40, textAlign: "center" }}>Loading...</div>}>
        <Routes>
          <Route path="/" element={<Home/>} />
          <Route path="/auth" element={<AuthPage/>} />
          <Route path="/dashboard" element={<RequireAuth><Dashboard/></RequireAuth>} />
          <Route path="/student" element={<StudentSubmit/>} />
          <Route path="/admin" element={<RequireRole role="admin"><AdminPage/></RequireRole>} />
          <Route path="/cross-batch" element={<RequireAuth><CrossBatchPage/></RequireAuth>} />
          <Route path="/student/comparison/:submissionId" element={<RequireAuth><StudentComparison/></RequireAuth>} />
        </Routes>
        </Suspense>
        </ErrorBoundary>
      </div>
    </AuthProvider>
  )
}
