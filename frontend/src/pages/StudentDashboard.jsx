import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAuthHeaders } from '../utils/auth'
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
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchMySubmissions() {
    setLoading(true)
    setError('')
    try {
      const headers = await getAuthHeaders()
      if (!headers.Authorization) { navigate('/auth'); return }
      const res = await fetch(`${API_BASE}/portal/my`, { headers, credentials: "include" })
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
        credentials: 'include',
        headers,
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
            <div className="loading-block"><div className="spinner"></div> Loading submissions...</div>
          ) : batches.length === 0 ? (
            <p className="section-copy">No submissions yet. Upload a file to a batch above.</p>
          ) : (
            batches.map(b => (
              <div key={b.batch_id} style={{ marginBottom: 24 }}>
                <h3 style={{ margin: '12px 0 8px', fontSize: 15 }}>{b.name}</h3>
                <table className="matrix-table" style={{ width: '100%', fontSize: 13 }}>
                  <thead>
                    <tr>
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
                        <td>{s.filename ? s.filename.split("_").slice(3).join("_") : (s.file_path?.split('/').pop() || '-')}</td>
                        <td>
                          <span className={`badge badge-${s.status === 'COMPLETED' ? 'success' : 'pending'}`}>
                            {s.status}
                          </span>
                        </td>
                        <td>{s.plagiarism_score != null ? `${(s.plagiarism_score * 100).toFixed(1)}%` : '-'}</td>
                        <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}</td>
                        <td><a href={`/student/comparison/${s.submission_id}`} className="btn" style={{ fontSize: 12, padding: '4px 8px' }}>View</a></td>
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
