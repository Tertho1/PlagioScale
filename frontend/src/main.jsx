import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import StudentSubmit from './pages/StudentSubmit'
import TeacherDashboard from './pages/TeacherDashboard'
import './index.css'
import './styles/portal.css'

function Home(){
  return (
    <div style={{maxWidth:1100, margin:'0 auto'}}>
      <section style={{padding:'56px 28px', borderRadius:24, background:'linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #38bdf8 100%)', color:'white', boxShadow:'0 24px 80px rgba(15,23,42,.22)'}}>
        <p style={{letterSpacing:'0.16em', textTransform:'uppercase', opacity:0.8, fontSize:12, marginBottom:14}}>PlagioScale Portal</p>
        <h1 style={{fontSize:'clamp(2.3rem, 6vw, 4.8rem)', lineHeight:1.02, margin:0, maxWidth:900}}>One place for student uploads and teacher similarity review.</h1>
        <p style={{maxWidth:760, marginTop:18, fontSize:18, lineHeight:1.6, opacity:0.92}}>
          Students upload assignments for plagiarism checking. Teachers create batches, monitor progress, and review the similarity matrix and exportable reports.
        </p>
      </section>

      <section style={{display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(260px, 1fr))', gap:20, marginTop:24}}>
        <Link to="/student" style={{textDecoration:'none', color:'inherit'}}>
          <div style={{padding:24, borderRadius:20, background:'white', border:'1px solid rgba(15,23,42,.08)', boxShadow:'0 16px 40px rgba(15,23,42,.08)', minHeight:180}}>
            <div style={{fontSize:13, textTransform:'uppercase', letterSpacing:'0.12em', color:'#2563eb', marginBottom:10}}>Student</div>
            <h2 style={{margin:'0 0 10px 0'}}>Submit a file</h2>
            <p style={{margin:0, color:'#334155', lineHeight:1.6}}>Upload a PDF or DOCX, enter the access code, and receive a plagiarism-check submission hash.</p>
          </div>
        </Link>

        <Link to="/teacher" style={{textDecoration:'none', color:'inherit'}}>
          <div style={{padding:24, borderRadius:20, background:'white', border:'1px solid rgba(15,23,42,.08)', boxShadow:'0 16px 40px rgba(15,23,42,.08)', minHeight:180}}>
            <div style={{fontSize:13, textTransform:'uppercase', letterSpacing:'0.12em', color:'#0f766e', marginBottom:10}}>Teacher</div>
            <h2 style={{margin:'0 0 10px 0'}}>Review similarity</h2>
            <p style={{margin:0, color:'#334155', lineHeight:1.6}}>Create an assignment batch, watch submissions arrive, compute the matrix, and export CSV results.</p>
          </div>
        </Link>
      </section>
    </div>
  )
}

function Root(){
  return (
    <BrowserRouter>
      <div style={{padding:20, minHeight:'100%'}}>
        <nav style={{display:'flex', gap:16, marginBottom:24, alignItems:'center'}}>
          <Link to="/" style={{fontWeight:700, textDecoration:'none'}}>Home</Link>
          <Link to="/student">Student Upload</Link>
          <Link to="/teacher">Teacher Dashboard</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Home/>} />
          <Route path="/student" element={<StudentSubmit/>} />
          <Route path="/teacher" element={<TeacherDashboard/>} />
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
