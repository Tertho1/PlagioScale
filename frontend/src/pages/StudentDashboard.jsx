import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../utils/config'
import { getAuthHeaders } from '../utils/auth'
import Dropzone from '../components/Dropzone'
import '../styles/portal.css'

export default function StudentDashboard() {
  const navigate = useNavigate()
  const { roll } = useAuth()
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBatch, setSelectedBatch] = useState('')
  const [file, setFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')
  const [selfCheck, setSelfCheck] = useState(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    fetchMySubmissions()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchMySubmissions() {
    setLoading(true)
    setError('')
    try {
      const headers = await getAuthHeaders()
      if (!headers.Authorization) { navigate('/auth'); return }
      const res = await fetch(`${API_BASE}/portal/my`, { headers, credentials: "include" })
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || await res.text() || 'Failed to load');
      }
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
    if (!roll) {
      setUploadStatus('Error: No roll number linked to your account')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadStatus('Error: File too large (max 10 MB)')
      return
    }
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!['.pdf','.docx','.txt','.md','.csv','.py','.java','.js','.ts'].includes(ext)) {
      setUploadStatus('Error: File type not allowed')
      return
    }
    setUploadStatus('Uploading...')
    try {
      const headers = await getAuthHeaders()
      const fd = new FormData()
      fd.append('file', file)
      fd.append('batch_id', selectedBatch)
      fd.append('roll', roll)
      const res = await fetch(`${API_BASE}/portal/submit`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: fd,
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || await res.text() || 'Upload failed');
      }
      const data = await res.json()
      setUploadStatus(`Uploaded: ${data.submission_hash || 'ok'}`)
      setFile(null)
      fetchMySubmissions()
    } catch (err) {
      setUploadStatus(`Error: ${err.message}`)
    }
  }

  async function handleSelfCheck() {
    if (!file || !selectedBatch) { setUploadStatus('Select a batch and a file to check'); return }
    setChecking(true)
    setSelfCheck(null)
    try {
      const headers = await getAuthHeaders()
      const fd = new FormData()
      fd.append('file', file)
      fd.append('batch_id', selectedBatch)
      const res = await fetch(`${API_BASE}/portal/self-check`, { method: 'POST', headers, body: fd, credentials: 'include' })
      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        throw new Error(errData?.detail || 'Check failed')
      }
      const data = await res.json()
      setSelfCheck(data)
    } catch (err) {
      setUploadStatus(`Error: ${err.message}`)
    } finally {
      setChecking(false)
    }
  }

  if (!roll) {
    return (
      <div className="page-shell">
        <section className="hero-card" style={{ marginBottom: 20 }}>
          <div className="eyebrow">My submissions</div>
          <h1>Roll number required</h1>
          <p className="hero-copy">
            Your account does not have a roll number. Please sign up with a roll number to submit assignments.
          </p>
        </section>
      </div>
    )
  }

  return (
    <div className="page-shell">

      <section className="hero-card" style={{ marginBottom: 20 }}>
        <div className="eyebrow">My submissions</div>
        <h1>Your assignments and submissions</h1>
        <p className="hero-copy">
          View your submissions across all batches. Upload new files to existing batches.
          Roll: <strong>{roll}</strong>
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
              <label>Roll Number</label>
              <input
                type="text"
                value={roll}
                disabled
              />
              <div className="field-help">Linked from your account profile</div>
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
              <button className="button-secondary" type="button" onClick={handleSelfCheck} disabled={!file || !selectedBatch || checking}>
                {checking ? 'Checking...' : 'Pre-check similarity'}
              </button>
            </div>
          </form>
          {selfCheck && (
            <div className="status-box" style={{ marginTop: 12 }}>
              {selfCheck.matches && selfCheck.matches.length > 0 ? (
                <>
                  <strong>Similar content found:</strong>
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                    {selfCheck.matches.slice(0, 3).map((m, i) => (
                      <li key={i}>Roll {m.roll}: {(m.max_similarity * 100).toFixed(1)}% similar</li>
                    ))}
                  </ul>
                  <div style={{ fontSize: 12, color: 'var(--text-soft)', marginTop: 6 }}>Consider revising before submitting.</div>
                </>
              ) : (
                <div style={{ color: 'var(--success)' }}>No significant similarity found with existing submissions.</div>
              )}
            </div>
          )}
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
            <div className="loading-block"><div className="spinner"></div> Loading submissions...</div>
          ) : batches.length === 0 ? (
            <p className="section-copy">No submissions yet. Upload a file to a batch above.</p>
          ) : (
            batches.map(b => (
              <div key={b.batch_id} style={{ marginBottom: 24 }}>
                <h3 style={{ margin: '12px 0 8px', fontSize: 15 }}>{b.name}</h3>
                <div style={{ maxHeight: 400, overflowY: 'auto', borderRadius: 12 }}>
                <table className="matrix-table" style={{ width: '100%', fontSize: 13 }}>
                  <thead>
                    <tr style={{ position: 'sticky', top: 0, background: 'var(--surface-strong)', zIndex: 1 }}>
                      <th>Roll</th>
                      <th>File</th>
                      <th>Status</th>
                      <th>Score</th>
                      <th>Submitted</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.submissions.map(s => (
                      <tr key={s.submission_id}>
                        <td>{s.roll || "—"}</td>
                        <td>{s.original_filename || (s.filename ? s.filename.split("_").slice(3).join("_") : (s.file_path?.split('/').pop() || '-'))}</td>
                        <td>
                          <span className={`badge badge-${s.status === 'COMPLETED' ? 'success' : 'pending'}`}>
                            {s.status}
                          </span>
                        </td>
                        <td>{s.plagiarism_score != null ? `${(s.plagiarism_score * 100).toFixed(1)}%` : '-'}</td>
                        <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}</td>
                        <td><Link to={`/student/comparison/${s.submission_id}`} className="btn" style={{ fontSize: 12, padding: '4px 8px' }}>View</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  )
}
