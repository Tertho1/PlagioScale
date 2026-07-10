import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import AuthPage from './pages/AuthPage'
import Dashboard from './pages/Dashboard'
import StudentSubmit from './pages/StudentSubmit'
import StudentDashboard from './pages/StudentDashboard'
import './index.css'
import './styles/portal.css'

function Home(){
  return (
    <div className="home-shell">
      <section className="home-hero">
        <div className="home-hero-copy">
          <p className="hero-kicker">PlagioScale workspace</p>
          <h1>Assignments, review, and submissions in one shared workspace.</h1>
          <p className="hero-summary">
            Sign in or create an account, then land on a dashboard where you can create assignments, review submissions, and drill into each assignment detail.
          </p>
          <div className="hero-actions">
            <Link to="/auth" className="button hero-button-primary">Login / Sign up</Link>
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
      <div className="root-shell">
        <nav className="root-nav">
          <Link to="/" className="root-nav-home">Home</Link>
          <Link to="/auth">Login / Sign up</Link>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/student">Submit</Link>
          <Link to="/student/dashboard">My Dashboard</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Home/>} />
          <Route path="/auth" element={<AuthPage/>} />
          <Route path="/dashboard" element={<Dashboard/>} />
          <Route path="/student" element={<StudentSubmit/>} />
          <Route path="/teacher" element={<Dashboard/>} />
          <Route path="/student/dashboard" element={<StudentDashboard/>} />
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
