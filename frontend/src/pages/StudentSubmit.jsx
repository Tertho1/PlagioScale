import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Dropzone from '../components/Dropzone'
import { getToken } from '../utils/auth'
import '../styles/portal.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const STUDENT_PROFILE_KEY = 'plagioscale_student_profile'

export default function StudentSubmit(){
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [roll, setRoll] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [isUploading, setIsUploading] = useState(false)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STUDENT_PROFILE_KEY) || '{}')
      if (saved.name) setName(saved.name)
      if (saved.email) setEmail(saved.email)
      if (saved.roll) setRoll(saved.roll)
    } catch {}
  }, [])

  async function handleSubmit(e){
    e.preventDefault()
    if(!file || !roll || !accessCode) { setStatus('Please provide roll, access code and a file'); return }
    const fd = new FormData()
    fd.append('file', file)
    fd.append('roll', roll)
    fd.append('name', name)
    fd.append('email', email)
    fd.append('access_code', accessCode)

    try {
      localStorage.setItem(STUDENT_PROFILE_KEY, JSON.stringify({ name, email, roll }))
    } catch {}

    setStatus('Uploading...')
    setIsUploading(true)
    try{
      const res = await fetch(`${API_BASE}/portal/submit`, { method: 'POST', body: fd })
      if(!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setStatus('Received: ' + (data.submission_hash || data.job_id || 'ok'))
    }catch(err){
      setStatus('Error: ' + err.message)
    }finally{
      setIsUploading(false)
    }
  }

  const token = getToken()

  return (
    <div className="page-shell">
      <div className="top-nav">
        <Link to="/" className="brand-mark">
          <span className="brand-badge">P</span>
          <span className="brand-copy">
            <strong>PlagioScale</strong>
            <span>Student submission portal</span>
          </span>
        </Link>
        <div className="nav-links">
          <Link to="/" className="nav-link">Home</Link>
          {token ? (
            <Link to="/dashboard" className="nav-link">Dashboard</Link>
          ) : (
            <Link to="/auth" className="nav-link">Login / Sign up</Link>
          )}
        </div>
      </div>

      <section className="hero-card" style={{marginBottom:20}}>
        <div className="eyebrow">Step 1 · Student upload</div>
        <h1>Submit your assignment in a few clear steps.</h1>
        <p className="hero-copy">
          Enter your details, use the access code given by your teacher, and upload a single PDF or DOCX file.
          The system will queue the submission and return a tracking hash.
        </p>
      </section>

      <div className="dashboard-layout">
        <section className="form-card">
          <div className="section-label">Submission form</div>
          <h2 className="section-title">Upload file for plagiarism checking</h2>
          <p className="section-copy">Use your roll number and the assignment access code. If you want, add your name and email once and they will be remembered on this device for future submissions.</p>

          <form onSubmit={handleSubmit} className="form-grid" style={{marginTop:20}}>
            <div className="field">
              <label>Roll Number</label>
              <input value={roll} onChange={e=>setRoll(e.target.value)} placeholder="e.g. 22045" />
            </div>

            <div className="field">
              <label>Assignment Access Code</label>
              <input value={accessCode} onChange={e=>setAccessCode(e.target.value)} placeholder="Enter the code from your teacher" />
            </div>

            <div className="field">
              <label>Student details</label>
              <div className="field-help" style={{marginBottom:10}}>
                Optional, remembered locally after the first entry.
              </div>
              <input value={name} onChange={e=>setName(e.target.value)} placeholder="Name (optional)" style={{marginBottom:10}} />
              <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email (optional)" type="email" />
            </div>

            <div className="field">
              <label>Document File</label>
              <Dropzone onFile={setFile} />
              <div className="field-help">Accepted formats: `.pdf` and `.docx`. One file per submission.</div>
            </div>

            {file && (
              <div className="selected-file">
                <div className="instruction-icon">✓</div>
                <div>
                  <strong>{file.name}</strong>
                  <span>{Math.max(1, Math.round(file.size / 1024))} KB ready to upload</span>
                </div>
              </div>
            )}

            <div className="toolbar">
              <button className="button" type="submit" disabled={isUploading}>
                {isUploading ? 'Uploading...' : 'Upload submission'}
              </button>
            </div>
          </form>

          <div className={`status-box ${status.startsWith('Error') ? 'error' : status.startsWith('Received') ? 'success' : ''}`} style={{marginTop:18}}>
            <strong>Status:</strong> {status || 'Ready to upload'}
          </div>
        </section>

        <aside className="guide-card">
          <div className="section-label">Quick note</div>
          <h2 className="section-title">Simple submission flow</h2>
          <p className="section-copy">
            The form stays minimal: roll number, access code, file, and optional identity details for the teacher record.
          </p>
          <div className="info-box" style={{marginTop:18}}>
            <strong>Teacher view</strong>
            <div className="small-copy" style={{marginTop:6}}>
              The dashboard will show the roll number together with your saved name and email when available.
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
