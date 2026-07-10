import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getAuthHeaders, getStoredEmail, clearToken } from '../utils/auth'
import Dropzone from '../components/Dropzone'
import '../styles/portal.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function StudentDashboard() {
  const navigate = useNavigate()
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBatch, setSelectedBatch] = useState('')
  const [roll, setRoll] = useState('')
  const [studentName, setStudentName] = useState('')
  const [file, setFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')

  useEffect(() => {
    fetchMySubmissions()
  }, [])

  async function fetchMySubmissions() {
    setLoading(true)
    setError('')
    try {
      const headers = await getAuthHeaders()
      if (!headers.Authorization) {
        navigate('/auth')
        return
      }
      const res = await fetch(`${API_BASE}/portal/my`, { headers })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setBatches(data.batches || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!file || !selectedBatch) {
      setUploadStatus('Select a batch and a file')
      return
    }
    if (!roll.trim()) {
      setUploadStatus('Roll number is required')
      return
    }
    setUploadStatus('Uploading...')
    try {
      const headers = await getAuthHeaders()
      const fd = new FormData()
      fd.append('file', file)
      fd.append('batch_id', selectedBatch)
      fd.append('roll', roll.trim())
      if (studentName.trim()) fd.append('name', studentName.trim())
      const res = await fetch(`${API_BASE}/portal/submit`, {
        method: 'POST',
        headers: { Authorization: headers.Authorization },
        body: fd,
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setUploadStatus(`Uploaded: ${data.submission_hash || 'ok'}`)
      setFile(null)
      fetchMySubmissions()
    } catch (err) {
      setUploadStatus(`Error: ${err.message}`)
    }
  }

  return (
    <div className="page-shell">
      <div className="top-nav">
        <Link to="/" className="brand-mark">
          <span className="brand-badge">P</span>
          <span className="brand-copy">
            <strong>PlagioScale</strong>
            <span>Student dashboard</span>
          </span>
        </Link>
        <div className="nav-links">
          <Link to="/" className="nav-link">Home</Link>
          <span className="nav-link" style={{cursor:'pointer'}} onClick={() => { clearToken(); navigate('/auth') }}>
            Logout
          </span>
        </div>
      </div>

      <section className="hero-card" style={{ marginBottom: 20 }}>
        <div className="eyebrow">My submissions</div>
        <h1>Your assignments and submissions</h1>
        <p className="hero-copy">
          View your submissions across all batches. Upload new files to existing batches.
        </p>
      </section>

      {error && (
        <div className="status-box error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div className="dashboard-layout">
        <section className="form-card">
          <div className="section-label">Upload</div>
          <h2 className="section-title">Submit a new file</h2>
          <form onSubmit={handleUpload} className="form-grid" style={{ marginTop: 20 }}>
            <div className="field">
              <label>Batch / Assignment</label>
              <select value={selectedBatch} onChange={e => setSelectedBatch(e.target.value)}>
                <option value="">— Select —</option>
                {batches.map(b => (
                  <option key={b.batch_id} value={b.batch_id}>{b.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Roll Number *</label>
              <input
                type="text"
                value={roll}
                onChange={e => setRoll(e.target.value)}
                placeholder="e.g. 2021001"
                required
              />
            </div>
            <div className="field">
              <label>Name (optional)</label>
              <input
                type="text"
                value={studentName}
                onChange={e => setStudentName(e.target.value)}
                placeholder="e.g. Jane Doe"
              />
            </div>
            <div className="field">
              <label>File</label>
              <Dropzone onFile={setFile} />
            </div>
            {file && (
              <div className="selected-file">
                <div className="instruction-icon">✓</div>
                <div>
                  <strong>{file.name}</strong>
                  <span>{Math.max(1, Math.round(file.size / 1024))} KB</span>
                </div>
              </div>
            )}
            <div className="toolbar">
              <button className="button" type="submit" disabled={!file || !selectedBatch}>
                Upload
              </button>
            </div>
          </form>
          {uploadStatus && (
            <div className={`status-box ${uploadStatus.startsWith('Error') ? 'error' : 'success'}`} style={{ marginTop: 12 }}>
              {uploadStatus}
            </div>
          )}
        </section>

        <section className="form-card">
          <div className="section-label">History</div>
          <h2 className="section-title">Your submissions</h2>
          {loading ? (
            <p className="section-copy">Loading...</p>
          ) : batches.length === 0 ? (
            <p className="section-copy">No submissions yet. Upload a file to a batch above.</p>
          ) : (
            batches.map(b => (
              <div key={b.batch_id} style={{ marginBottom: 24 }}>
                <h3 style={{ margin: '12px 0 8px', fontSize: 15 }}>{b.name}</h3>
                <table className="matrix-table" style={{ width: '100%', fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Status</th>
                      <th>Score</th>
                      <th>Submitted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.submissions.map(s => (
                      <tr key={s.submission_id}>
                        <td>{s.filename || s.file_path?.split('/').pop() || '-'}</td>
                        <td>
                          <span className={`badge badge-${s.status === 'COMPLETED' ? 'success' : 'pending'}`}>
                            {s.status}
                          </span>
                        </td>
                        <td>{s.plagiarism_score != null ? `${(s.plagiarism_score * 100).toFixed(1)}%` : '-'}</td>
                        <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  )
}
