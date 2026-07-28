import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { clearToken, getAuthHeaders, getStoredEmail, getToken } from "../utils/auth";
import { useBatchProgress } from "../utils/websocket";
import BlindReviewToggle from "../components/BlindReviewToggle";
import CollusionGraph from "../components/CollusionGraph";
import SimilarityMatrix from "../components/SimilarityMatrix";
import MatrixViewer from "../components/MatrixViewer";
import "../styles/portal.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function formatDate(value) {
  if (!value) return "Recently";
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return value;
  }
}

function AssignmentCard({ item, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`assignment-card ${active ? "assignment-card-active" : ""}`}
    >
      <div className="assignment-card-header">
        <div>
          <div className="assignment-title">{item.name}</div>
          <div className="assignment-subtitle">{item.batch_id}</div>
        </div>
        <span className="assignment-pill">{item.expected_count || 0} expected</span>
      </div>
      <div className="assignment-meta">
        <span>{formatDate(item.created_at)}</span>
        <span>{item.owner_user_id ? "Owned" : "Shared"}</span>
      </div>
    </button>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const token = getToken();
  const email = getStoredEmail();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [assignmentName, setAssignmentName] = useState("");
  const [expectedCount, setExpectedCount] = useState(30);
  const [ownedAssignments, setOwnedAssignments] = useState([]);
  const [sharedAssignments, setSharedAssignments] = useState([]);
  const [selectedId, setSelectedId] = useState(searchParams.get("batch") || "");
  const [selected, setSelected] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [labels, setLabels] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [creating, setCreating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [computing, setComputing] = useState(false);
  const [viewer, setViewer] = useState({ open: false, left: null, right: null, similarity: 0 });
  const [blindReview, setBlindReview] = useState(false);

  const wsProgress = useBatchProgress(selectedId);

  const displayLabels = useMemo(() => {
    if (!blindReview || !labels.length) return labels;
    return labels.map((_, idx) => `Submission ${idx + 1}`);
  }, [blindReview, labels]);

  const stats = useMemo(() => {
    const total = ownedAssignments.length + sharedAssignments.length;
    return {
      total,
      owned: ownedAssignments.length,
      shared: sharedAssignments.length,
      submissions: submissions.length,
    };
  }, [ownedAssignments.length, sharedAssignments.length, submissions.length]);

  useEffect(() => {
    if (wsProgress.processed > 0 && selected) {
      loadAssignmentDetails(selectedId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsProgress.processed, wsProgress.total]);

  async function loadAssignments() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/portal/assignments`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to load assignments");
      const owned = (data.owned || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      const shared = (data.shared || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setOwnedAssignments(owned);
      setSharedAssignments(shared);
      setSelectedId((id) => id || (owned[0]?.batch_id || shared[0]?.batch_id || ""));
    } catch (error) {
      setError(error.message);
      if (error.message?.includes("authorization") || error.message?.includes("token")) {
        clearToken();
        navigate("/auth");
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadAssignmentDetails(batchId) {
    if (!batchId || !token) return;
    setRefreshing(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/portal/assignments/${batchId}`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to load assignment");

      setSelected(data.assignment);
      setSubmissions(data.submissions || []);

      const mres = await fetch(`${API_BASE}/portal/similarity-matrix/${batchId}`, { headers: await getAuthHeaders(), credentials: "include" });
      if (mres.ok) {
        const mjson = await mres.json();
        const matrixObj = mjson.matrix || {};
        const ids = Object.keys(matrixObj);
        setMatrix(ids.length ? ids.map((i) => ids.map((j) => matrixObj[i][j] || 0)) : null);

        const sfetch = await fetch(`${API_BASE}/portal/submissions/${batchId}?limit=500&offset=0`, { headers: await getAuthHeaders(), credentials: "include" });
        let labelsMap = {};
        if (sfetch.ok) {
          const sjson = await sfetch.json();
          (sjson.submissions || []).forEach((submission) => {
            const parts = [submission.roll];
            if (submission.name) parts.push(submission.name);
            if (submission.email) parts.push(submission.email);
            labelsMap[submission.submission_id] = parts.filter(Boolean).join(" · ") || submission.submission_id;
          });
        }
        setLabels(ids.map((id) => labelsMap[id] || id));
      } else {
        setMatrix(null);
        setLabels([]);
      }
    } catch (error) {
      setError(error.message);
    } finally {
      setRefreshing(false);
    }
  }

  async function createAssignment(event) {
    event.preventDefault();
    if (!token) return navigate("/auth");

    setCreating(true);
    setError("");
    try {
      const headers = {
        "Content-Type": "application/json",
        ...(await getAuthHeaders()),
      };
      const response = await fetch(`${API_BASE}/portal/assignments`, {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({ name: assignmentName, expected_count: Number(expectedCount) || 0 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to create assignment");
      setAssignmentName("");
      await loadAssignments();
      setSelectedId(data.batch_id);
      await loadAssignmentDetails(data.batch_id);
    } catch (error) {
      setError(error.message);
    } finally {
      setCreating(false);
    }
  }

  async function computeSimilarity() {
    if (!selectedId) return;
    console.log("[Compute] Starting compute for batch:", selectedId);
    setError("");
    setComputing(true);
    try {
      console.log("[Compute] POST /portal/compute-similarity/");
      const response = await fetch(`${API_BASE}/portal/compute-similarity/${selectedId}`, { method: "POST", headers: await getAuthHeaders(), credentials: "include" });
      console.log("[Compute] Response status:", response.status);
      const data = await response.json().catch(() => ({}));
      console.log("[Compute] Response body:", data);
      if (!response.ok) {
        setError(data.detail || "Failed to queue compute");
        setComputing(false);
        return;
      }
      const jobId = data.job_id;
      console.log("[Compute] Job queued, jobId:", jobId);
      let status = null;
      let jobError = null;
      for (let i = 0; i < 300; i++) {
        try {
          const sres = await fetch(`${API_BASE}/status/${jobId}`, { credentials: "include" });
          if (sres.ok) {
            const sjson = await sres.json();
            console.log(`[Compute] Poll ${i + 1}: status=`, sjson.status, "error=", sjson.error);
            status = sjson.status;
            jobError = sjson.error || null;
            if (status === "COMPLETED" || status === "FAILED") {
              console.log("[Compute] Terminal status reached:", status);
              break;
            }
          } else {
            console.log(`[Compute] Poll ${i + 1}: status endpoint returned ${sres.status}`);
          }
        } catch (e) { console.log(`[Compute] Poll ${i + 1}: fetch error:`, e); }
        await new Promise((r) => setTimeout(r, 2000));
      }
      console.log("[Compute] Poll loop ended. Final status:", status, "jobError:", jobError);
      if (status !== "COMPLETED") {
        setError(jobError || "Compute failed or timed out");
        setComputing(false);
        return;
      }
      console.log("[Compute] Job completed, refreshing assignment details");
      await loadAssignmentDetails(selectedId);
      console.log("[Compute] Assignment details refreshed successfully");
    } catch (e) {
      console.log("[Compute] Unhandled error:", e);
      setError(e?.message || "Compute failed");
    } finally {
      setComputing(false);
    }
  }

  const handleCellClick = useCallback(async (rowIdx, colIdx, cellValue) => {
    const ids = Object.keys(Object.fromEntries(submissions.map(s => [s.submission_id, s])));
    const leftId = ids[rowIdx];
    const rightId = ids[colIdx];
    const leftLabel = displayLabels[rowIdx];
    const rightLabel = displayLabels[colIdx];

    let leftText = "";
    let rightText = "";

    async function fetchText(subId) {
      try {
        const res = await fetch(
          `${API_BASE}/portal/submissions/${selectedId}/${subId}/text`,
          { credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          return data.text || "";
        }
      } catch {
        // fallback to empty
      }
      return "";
    }

    if (leftId) leftText = await fetchText(leftId);
    if (rightId) rightText = await fetchText(rightId);

    setViewer({
      open: true,
      left: { id: leftId, label: leftLabel, text: leftText },
      right: { id: rightId, label: rightLabel, text: rightText },
      similarity: cellValue,
    });
  }, [submissions, labels, selectedId]);

  useEffect(() => {
    if (!token) {
      navigate("/auth");
      return;
    }
    loadAssignments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!selectedId) return;
    setSearchParams(selectedId ? { batch: selectedId } : {}, { replace: true });
    loadAssignmentDetails(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  if (!token) return null;

  return (
    <div className="page-shell dashboard-shell">

      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <div className="eyebrow">Workspace</div>
          <h1>Manage assignments, review submissions, and drill into each batch.</h1>
          <p>
            Signed in as <span className="mono">{email || "user"}</span>.
          </p>
          <div className="dashboard-select-bar">
            <select
              value={selectedId || ""}
              onChange={(e) => setSelectedId(e.target.value)}
              className="assignment-select"
            >
              {!selectedId && <option value="">Select an assignment...</option>}
              {ownedAssignments.map((a) => (
                <option key={a.batch_id} value={a.batch_id}>{a.name} (owned)</option>
              ))}
              {sharedAssignments.map((a) => (
                <option key={a.batch_id} value={a.batch_id}>{a.name} (shared)</option>
              ))}
            </select>
            <div className="toolbar-actions">
              <BlindReviewToggle enabled={blindReview} onToggle={() => setBlindReview((v) => !v)} />
              <button className="button-secondary button-sm" type="button" onClick={() => selectedId && loadAssignmentDetails(selectedId)} disabled={refreshing}>
                {refreshing ? "Refreshing..." : "Refresh"}
              </button>
              <button className="button button-sm" type="button" onClick={computeSimilarity} disabled={!selectedId || computing}>
                {computing ? "Computing..." : "Compute similarity"}
              </button>
            </div>
          </div>
        </div>
        <div className="dashboard-hero-stats">
          <div className="dashboard-stat">
            <span>{stats.total}</span>
            <small>Assignments</small>
          </div>
          <div className="dashboard-stat">
            <span>{stats.owned}</span>
            <small>Owned</small>
          </div>
          <div className="dashboard-stat">
            <span>{stats.submissions}</span>
            <small>Submissions in view</small>
          </div>
        </div>
      </section>

      {error && (
        <div className="status-box error" style={{ margin: "0 auto", maxWidth: 960 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {wsProgress.processed > 0 && wsProgress.total > 0 && (
        <div className="status-box success" style={{ margin: "0 auto", maxWidth: 960 }}>
          Progress: {wsProgress.processed} / {wsProgress.total} submissions processed
          {wsProgress.processed >= wsProgress.total ? " ✓ Complete" : ""}
        </div>
      )}

      <section className="dashboard-grid">
        <aside className="dashboard-panel dashboard-panel-list">
          <div className="section-label">Your work</div>
          <h2 className="section-title">Assignments</h2>

          <form onSubmit={createAssignment} className="mini-create-form">
            <input
              value={assignmentName}
              onChange={(e) => setAssignmentName(e.target.value)}
              placeholder="New assignment name"
            />
            <input
              type="number"
              min="0"
              value={expectedCount}
              onChange={(e) => setExpectedCount(e.target.value)}
              placeholder="Expected submissions"
            />
            <button className="button" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create assignment"}
            </button>
          </form>

          <div className="assignment-list-block">
            <div className="list-heading">Owned</div>
            <div className="assignment-list">
              {loading
                ? Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton skeleton-card" />)
                : ownedAssignments.map((item) => (
                <AssignmentCard key={item.batch_id} item={item} active={selectedId === item.batch_id} onClick={() => setSelectedId(item.batch_id)} />
              ))}
              {!loading && ownedAssignments.length === 0 && <div className="empty-state">No owned assignments yet.</div>}
            </div>
          </div>

          <div className="assignment-list-block">
            <div className="list-heading">Shared</div>
            <div className="assignment-list">
              {loading
                ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="skeleton skeleton-card" />)
                : sharedAssignments.map((item) => (
                <AssignmentCard key={item.batch_id} item={item} active={selectedId === item.batch_id} onClick={() => setSelectedId(item.batch_id)} />
              ))}
              {!loading && sharedAssignments.length === 0 && <div className="empty-state">No shared assignments.</div>}
            </div>
          </div>
        </aside>

        <main className="dashboard-panel dashboard-panel-detail">
          <div className="detail-header">
            <div>
              <div className="section-label">Assignment detail</div>
              <h2 className="section-title">{selected?.name || "Select an assignment"}</h2>
              <p className="section-copy">
                {selected ? `${submissions.length} submissions · ${selected.batch_id}` : "Open an assignment to see submissions, similarity, and summary details."}
              </p>
            </div>
            <div className="detail-actions">
              <BlindReviewToggle enabled={blindReview} onToggle={() => setBlindReview((v) => !v)} />
              <button className="button-secondary" type="button" onClick={() => selectedId && loadAssignmentDetails(selectedId)} disabled={refreshing}>
                {refreshing ? "Refreshing..." : "Refresh"}
              </button>
              <button className="button" type="button" onClick={computeSimilarity} disabled={!selectedId || computing}>
                {computing ? "Computing..." : "Compute similarity"}
              </button>
            </div>
          </div>

          {selected ? (
            <>
              <div className="detail-cards">
                <div className="detail-card">
                  <span className="detail-label">Access code</span>
                  <strong className="mono">{selected.access_code}</strong>
                </div>
                <div className="detail-card">
                  <span className="detail-label">Expected</span>
                  <strong>{selected.expected_count || 0}</strong>
                </div>
                <div className="detail-card">
                  <span className="detail-label">Submitted</span>
                  <strong>{submissions.length}</strong>
                </div>
              </div>

              <div className="submissions-table">
                {submissions.length > 0 ? submissions.map((submission, idx) => {
                  const aiScore = submission.ai_score != null ? submission.ai_score : null;
                  let aiBadge = null;
                  if (aiScore != null && aiScore >= 0) {
                    const pct = (aiScore * 100).toFixed(0);
                    const cls = aiScore > 0.7 ? 'ai-badge-red' : aiScore > 0.3 ? 'ai-badge-yellow' : 'ai-badge-green';
                    aiBadge = <span className={`ai-badge ${cls}`} title={`AI detection confidence: ${pct}%`}>AI {pct}%</span>;
                  }
                  return (
                    <div key={submission.submission_id} className="submission-row">
                      <div>
                        <strong>{blindReview ? `Submission ${idx + 1}` : submission.roll}</strong>
                        <div className="small-copy">{blindReview ? "—" : (submission.name || "Name not provided")}</div>
                        <div className="small-copy">{blindReview ? "—" : (submission.email || "Email not provided")}</div>
                      </div>
                      <div className="row-meta">
                        {aiBadge}
                        <span>{submission.status || "ACTIVE"}</span>
                        <span className="mono">{submission.submission_id.slice(0, 8)}</span>
                      </div>
                    </div>
                  );
                }) : <div className="empty-state">No submissions for this assignment yet.</div>}
              </div>

              <div className="matrix-card matrix-card-compact">
                <div className="section-label">Similarity matrix</div>
                <SimilarityMatrix matrix={matrix} labels={displayLabels} onCellClick={handleCellClick} />
              </div>

              <CollusionGraph matrix={matrix} labels={displayLabels} />
            </>
          ) : (
            <div className="empty-state empty-state-large">
              Choose an assignment from the left or create a new one to begin.
            </div>
          )}
        </main>
      </section>

      <MatrixViewer
        open={viewer.open}
        leftSubmission={viewer.left}
        rightSubmission={viewer.right}
        similarity={viewer.similarity}
        batchId={selectedId}
        onClose={() => setViewer({ ...viewer, open: false })}
      />
    </div>
  );
}