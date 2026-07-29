import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import SimilarityMatrix from "../components/SimilarityMatrix";
import MatrixViewer from "../components/MatrixViewer";
import "../styles/portal.css";
import { getAuthHeaders, getToken, getStoredEmail } from "../utils/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function TeacherDashboard() {
  const navigate = useNavigate();
  const [assignName, setAssignName] = useState("");
  const [batchId, setBatchId] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [progress, setProgress] = useState({ processed: 0, total: 0 });
  const [matrix, setMatrix] = useState(null);
  const [labels, setLabels] = useState([]);
  const [error, setError] = useState("");
  const [computing, setComputing] = useState(false);
  const [viewer, setViewer] = useState({
    open: false,
    left: null,
    right: null,
    similarity: 0,
  });
  const wsRef = useRef(null);
  const authToken = getToken();
  const authEmail = getStoredEmail();

  async function createAssignment(e) {
    e.preventDefault();
    if (!authToken) {
      navigate("/auth");
      return;
    }
    const headers = {
      "Content-Type": "application/json",
      ...(await getAuthHeaders()),
    };
    const res = await fetch(`${API_BASE}/portal/assignments`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify({ name: assignName, expected_count: 50 }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setError(err.detail || "Failed to create assignment");
      return;
    }
    const data = await res.json();
    setBatchId(data.batch_id);
    setAccessCode(data.access_code);
    setProgress({ processed: 0, total: 50 });
    // initialize labels as placeholders
    setLabels(Array.from({ length: 50 }, (_, i) => `S${i + 1}`));
  }

  useEffect(() => {
    if (!batchId) return;
    try {
      const token = getToken();
      const wsUrl = API_BASE.replace("http", "ws") + `/portal/ws/${batchId}`;
      const ws = new WebSocket(token ? `${wsUrl}?token=${token}` : wsUrl);
      ws.onmessage = (ev) => {
        try {
          const d = JSON.parse(ev.data);
          setProgress(d);
        } catch (e) { /* ignore ws parse error */ }
      };
      wsRef.current = ws;
      return () => ws.close();
    } catch (e) {
      console.warn("ws failed", e);
    }
  }, [batchId]);

  function handleGenerateMock() {
    computeAndFetch();
  }

  async function computeAndFetch() {
    if (!batchId) { setError("Create or enter a batch id first"); return; }
    try {
      setComputing(true);
      // enqueue batch compute job
      const post = await fetch(
        `${API_BASE}/portal/compute-similarity/${batchId}`,
        { method: "POST", credentials: "include" },
      );
      const pdata = await post.json().catch(() => ({}));
      if (!post.ok) {
        setComputing(false);
        setError(pdata.detail || "Compute enqueue failed");
        return;
      }
      const jobId = pdata.job_id;

      // poll job status until COMPLETED or FAILED
      let status = null;
      for (let i = 0; i < 300; i++) {
        // max ~10 minutes with 2s interval
        try {
          const sres = await fetch(`${API_BASE}/status/${jobId}`, { credentials: "include" });
          if (sres.ok) {
            const sjson = await sres.json();
            status = sjson.status;
            if (status === "COMPLETED") break;
            if (status === "FAILED") break;
          }
        } catch (e) {
          /* ignore transient */
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
      setComputing(false);
      if (status !== "COMPLETED") { setError("Compute failed or timed out"); return; }

      // fetch similarity matrix after completion
      const mres = await fetch(
        `${API_BASE}/portal/similarity-matrix/${batchId}`,
        { credentials: "include" },
      );
      if (!mres.ok) { setError("Failed fetching matrix"); return; }
      const mjson = await mres.json();
      const matrixObj = mjson.matrix;
      const ids = Object.keys(matrixObj);
      const mat = ids.map((i) => ids.map((j) => matrixObj[i][j] || 0));

      // fetch submissions to get friendly labels (roll/name)
      const sfetch = await fetch(`${API_BASE}/portal/submissions/${batchId}`, { credentials: "include" });
      let labelsMap = {};
      if (sfetch.ok) {
        const sjson = await sfetch.json();
        sjson.submissions.forEach((s) => {
          const pieces = [s.roll];
          if (s.name) pieces.push(s.name);
          if (s.email) pieces.push(s.email);
          labelsMap[s.submission_id] = pieces.filter(Boolean).join(" · ") || s.submission_id;
        });
      }
      const lbls = ids.map((id) => labelsMap[id] || id);
      setLabels(lbls);
      setMatrix(mat);
    } catch (e) {
      console.error(e);
      setComputing(false);
      setError(e?.message || "Compute failed");
    }
  }

  function handleCellClick(i, j, cell) {
    setViewer({
      open: true,
      left: { id: i, label: labels[i], snippet: "(mock) left snippet..." },
      right: { id: j, label: labels[j], snippet: "(mock) right snippet..." },
      similarity: cell,
    });
  }

  async function handleExportCSV() {
    if (!batchId) { setError("Create or enter a batch id first"); return; }
    const url = `${API_BASE}/portal/export/${batchId}`;
    window.open(url, "_blank");
  }

  return (
    <div className="page-shell">

      {!authToken ? (
        <section className="hero-card" style={{ marginBottom: 20 }}>
          <div className="eyebrow">Authentication required</div>
          <h1>Sign in before creating or reviewing batches.</h1>
          <p className="hero-copy">
            Assignment creation is protected so only signed-in users can create and own batches.
          </p>
          <div className="toolbar">
            <Link to="/auth" className="button">
              Go to login
            </Link>
          </div>
        </section>
      ) : (
        <section className="hero-card" style={{ marginBottom: 20 }}>
          <div className="eyebrow">Step 2 · Review</div>
          <h1>
            Create a batch, track submissions, and inspect similarity at a glance.
          </h1>
          <p className="hero-copy">
            Signed in as <span className="mono">{authEmail || "user"}</span>. Set up an assignment batch, share the access code with students, and use the matrix to spot possible overlap.
          </p>
        </section>
      )}

      {error && (
        <div className="status-box error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div className="metric-row" style={{ marginBottom: 20 }}>
        <div className="metric-card">
          <div className="metric-value">{progress.total || 0}</div>
          <div className="metric-label">Expected submissions</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{progress.processed || 0}</div>
          <div className="metric-label">Processed so far</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{batchId ? "Live" : "Idle"}</div>
          <div className="metric-label">Batch status</div>
        </div>
      </div>

      <div className="dashboard-layout">
        <section className="surface">
          <div className="section-label">Batch setup</div>
          <h2 className="section-title">Create an assignment batch</h2>
          <p className="section-copy">
            Give the batch a clear name. When you create it, the portal will generate a shareable access code for students.
          </p>

          <form
            onSubmit={createAssignment}
            className="form-grid"
            style={{ marginTop: 20 }}
          >
            <div className="field">
              <label>Assignment name</label>
              <input
                placeholder="e.g. Essay 1 - Literature Review"
                value={assignName}
                onChange={(e) => setAssignName(e.target.value)}
              />
              <div className="field-help">
                Use a meaningful title so students and reports stay easy to
                identify.
              </div>
            </div>

            <div className="toolbar">
              <button type="submit" className="button">
                Create batch
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={handleGenerateMock}
                disabled={!batchId}
              >
                Refresh similarity
              </button>
            </div>
          </form>

          {batchId && (
            <div className="info-box" style={{ marginTop: 18 }}>
              <strong>Batch created</strong>
              <div className="small-copy" style={{ marginTop: 6 }}>
                Share this access code with students:{" "}
                <span className="mono">{accessCode}</span>
              </div>
              <div className="small-copy" style={{ marginTop: 6 }}>
                Batch ID: <span className="mono">{batchId}</span>
              </div>
            </div>
          )}
        </section>

        <aside className="guide-card">
          <div className="section-label">How it works</div>
          <h2 className="section-title">Review flow</h2>
          <ul className="instruction-list" style={{ marginTop: 18 }}>
            <li>
              <span className="instruction-icon">1</span>
              <div>
                <strong>Create the batch</strong>
                <span>
                  The system generates a batch ID and access code for your
                  class.
                </span>
              </div>
            </li>
            <li>
              <span className="instruction-icon">2</span>
              <div>
                <strong>Wait for submissions</strong>
                <span>
                  Watch the progress bar as students upload files to the batch.
                </span>
              </div>
            </li>
            <li>
              <span className="instruction-icon">3</span>
              <div>
                <strong>Inspect the matrix</strong>
                <span>
                  Click any cell to review the comparison details in a modal.
                </span>
              </div>
            </li>
          </ul>

          <div className="subtle-divider"></div>
          <div className="note-box">
            <strong>Tip</strong>
            <div className="small-copy" style={{ marginTop: 6 }}>
              The matrix is most useful once several students have submitted.
              You can still export the CSV at any time.
            </div>
          </div>
        </aside>
      </div>

      <section className="overview-card" style={{ marginTop: 20 }}>
        <div className="section-label">Batch progress</div>
        <div
          className="toolbar"
          style={{
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 10,
          }}
        >
          <h2 className="section-title" style={{ margin: 0 }}>
            Live submission progress
          </h2>
          <div className="small-copy">
            {progress.processed} of {progress.total} processed
          </div>
        </div>
        <div className="progress-shell">
          <div
            className="progress-bar"
            style={{
              width: progress.total
                ? `${(progress.processed / progress.total) * 100}%`
                : "0%",
            }}
          ></div>
        </div>
      </section>

      <section className="matrix-card" style={{ marginTop: 20 }}>
        <div className="section-label">Similarity matrix</div>
        <div
          className="toolbar"
          style={{
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 14,
          }}
        >
          <div>
            <h2 className="section-title" style={{ marginBottom: 4 }}>
              Document similarity view
            </h2>
            <p className="section-copy">
              Use the buttons below to refresh the matrix and download a CSV
              report for batch review.
            </p>
          </div>
          <div className="mini-toolbar">
            <button
              onClick={computeAndFetch}
              className="button-secondary"
              disabled={computing}
            >
              {computing ? "Computing..." : "Refresh matrix"}
            </button>
            <button onClick={handleExportCSV} className="button">
              Export CSV
            </button>
          </div>
        </div>
        <SimilarityMatrix
          matrix={matrix}
          labels={labels}
          onCellClick={handleCellClick}
        />
      </section>

      <MatrixViewer
        open={viewer.open}
        leftSubmission={viewer.left}
        rightSubmission={viewer.right}
        similarity={viewer.similarity}
        onClose={() => setViewer({ ...viewer, open: false })}
      />
    </div>
  );
}
