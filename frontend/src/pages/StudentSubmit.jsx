import { useState } from 'react'
import { Link } from 'react-router-dom'
import Dropzone from '../components/Dropzone'
import '../styles/portal.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function StudentSubmit(){
  const [name, setName] = useState('')
  const [roll, setRoll] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [isUploading, setIsUploading] = useState(false)

  async function handleSubmit(e){
    e.preventDefault()
    if(!file || !roll || !accessCode) { setStatus('Please provide roll, access code and a file'); return }
    const fd = new FormData()
    fd.append('file', file)
    fd.append('roll', roll)
    fd.append('name', name)
    fd.append('access_code', accessCode)

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
          <Link to="/teacher" className="nav-link">Teacher Dashboard</Link>
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
          <p className="section-copy">Make sure your file is complete before uploading. You can use the access code exactly as provided by your teacher.</p>

          <form onSubmit={handleSubmit} className="form-grid" style={{marginTop:20}}>
            <div className="field">
              <label>Student Name</label>
              <input value={name} onChange={e=>setName(e.target.value)} placeholder="Your full name" />
              <div className="field-help">Optional, but it helps the teacher identify your submission.</div>
            </div>

            <div className="field">
              <label>Roll Number</label>
              <input value={roll} onChange={e=>setRoll(e.target.value)} placeholder="e.g. 22045" />
            </div>

            <div className="field">
              <label>Assignment Access Code</label>
              <input value={accessCode} onChange={e=>setAccessCode(e.target.value)} placeholder="Enter the code from your teacher" />
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
              <Link to="/teacher" className="button-secondary">Go to Teacher Dashboard</Link>
            </div>
          </form>

          <div className={`status-box ${status.startsWith('Error') ? 'error' : status.startsWith('Received') ? 'success' : ''}`} style={{marginTop:18}}>
            <strong>Status:</strong> {status || 'Ready to upload'}
          </div>
        </section>

        <aside className="guide-card">
          <div className="section-label">Before uploading</div>
          <h2 className="section-title">What to prepare</h2>
          <ul className="instruction-list" style={{marginTop:18}}>
            <li>
              <span className="instruction-icon">1</span>
              <div><strong>Get your access code</strong><span>Use the code provided by your teacher for the correct assignment batch.</span></div>
            </li>
            <li>
              <span className="instruction-icon">2</span>
              <div><strong>Choose the right file</strong><span>Upload only the final PDF or DOCX version of your work.</span></div>
            </li>
            <li>
              <span className="instruction-icon">3</span>
              <div><strong>Submit once</strong><span>After uploading, keep the returned submission hash for reference.</span></div>
            </li>
          </ul>

          <div className="subtle-divider"></div>
          <div className="info-box">
            <strong>Need help?</strong>
            <div className="small-copy" style={{marginTop:6}}>
              If your teacher has not shared an access code, you won’t be able to submit yet.
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
