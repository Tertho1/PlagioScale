import { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../utils/config'
import { getAuthHeaders } from '../utils/auth'
import Dropzone from '../components/Dropzone'

import '../styles/portal.css'

export default function StudentSubmit(){
  const { roll: profileRoll, name: profileName, email: profileEmail } = useAuth()
  const [manualRoll, setManualRoll] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [assignmentInfo, setAssignmentInfo] = useState(null)

  // Profile roll wins; otherwise accept a one-time manual entry.
  const roll = profileRoll || manualRoll.trim()

  useEffect(() => {
    const code = accessCode.trim();
    if (!code) { setAssignmentInfo(null); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/portal/assignment-info?access_code=${encodeURIComponent(code)}`);
        if (res.ok) setAssignmentInfo(await res.json());
        else setAssignmentInfo(null);
      } catch { setAssignmentInfo(null); }
    }, 400);
    return () => clearTimeout(timer);
  }, [accessCode]);

  const isOverdue = assignmentInfo?.due_date && new Date(assignmentInfo.due_date) < new Date();

  async function handleSubmit(e){
    e.preventDefault()
    if(!roll) { setStatus('Error: Please enter your roll number'); return }
    if(!file || !accessCode) { setStatus('Please provide an access code and a file'); return }
    if (!accessCode.trim()) { setStatus('Error: Access code is required'); return }
    if (!file) { setStatus('Error: Please select a file to upload'); return }
    if (file.size > 10 * 1024 * 1024) { setStatus('Error: File too large (max 10 MB)'); return }
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!['.pdf','.docx','.txt','.md','.csv','.py','.java','.js','.ts'].includes(ext)) {
      setStatus('Error: File type not allowed')
      return
    }
    const fd = new FormData()
    fd.append('file', file)
    fd.append('roll', roll)
    fd.append('access_code', accessCode)

    setStatus('Uploading...')
    setIsUploading(true)
    try{
      const headers = await getAuthHeaders()
      const res = await fetch(`${API_BASE}/portal/submit`, {
        method: 'POST',
        body: fd,
        credentials: 'include',
        headers,
      })
      if(!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || await res.text() || 'Upload failed');
      }
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

      <section className="hero-card" style={{marginBottom:20}}>
        <div className="eyebrow">Step 1 · Student upload</div>
        <h1>Submit your assignment in a few clear steps.</h1>
        <p className="hero-copy">
          Use the access code given by your teacher and upload a single PDF or DOCX file.
          {profileRoll
            ? <> Your roll number (<strong>{profileRoll}</strong>) is taken from your account.</>
            : ' Enter your roll number below — it identifies your submission.'}
        </p>
      </section>

      <div className="dashboard-layout">
        <section className="form-card">
          <div className="section-label">Submission form</div>
          <h2 className="section-title">Upload file for plagiarism checking</h2>
          <p className="section-copy">
            Logged in as <strong>{profileName || profileEmail}</strong>
            {roll ? <> — Roll: <strong>{roll}</strong></> : null}
          </p>

          <form onSubmit={handleSubmit} className="form-grid" style={{marginTop:20}}>
            {!profileRoll && (
              <div className="field">
                <label htmlFor="manual-roll">Roll Number</label>
                <input
                  id="manual-roll"
                  value={manualRoll}
                  onChange={e=>setManualRoll(e.target.value)}
                  placeholder="e.g. 22045"
                  autoComplete="off"
                  required
                />
                <div className="field-help">Your account has no roll number yet — enter it here for this submission.</div>
              </div>
            )}

            <div className="field">
              <label>Assignment Access Code</label>
              <input value={accessCode} onChange={e=>setAccessCode(e.target.value)} placeholder="Enter the code from your teacher" />
              {assignmentInfo && (
                <div style={{ marginTop: 6, fontSize: 13 }}>
                  <div><strong>{assignmentInfo.name}</strong></div>
                  {assignmentInfo.due_date && (
                    <div style={{ color: isOverdue ? "var(--danger)" : "var(--text-soft)", marginTop: 2 }}>
                      Deadline: {new Date(assignmentInfo.due_date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                      {isOverdue && <strong style={{ marginLeft: 6 }}>(overdue — submission may be rejected)</strong>}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="field">
              <label>Document File</label>
              <Dropzone onFile={setFile} />
              <div className="field-help">Accepted formats: PDF, DOCX, TXT, MD, CSV, PY, Java, JS, TS. One file per submission.</div>
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
            The form stays minimal: access code and file. Your roll number is linked to your account — no one can impersonate you.
          </p>
          <div className="info-box" style={{marginTop:18}}>
            <strong>Teacher view</strong>
            <div className="small-copy" style={{marginTop:6}}>
              The dashboard will show your roll number and name from your account profile.
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
