import PropTypes from "prop-types";
import React, { Suspense, memo, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE } from "../utils/config";
import { getAuthHeaders, getStoredEmail } from "../utils/auth";
import { showToast } from "../components/Toast";
import useAssignments from "../hooks/useAssignments";
import useAssignmentDetails from "../hooks/useAssignmentDetails";
import useSimilarityCompute from "../hooks/useSimilarityCompute";
import useMatrixViewer from "../hooks/useMatrixViewer";
import BlindReviewToggle from "../components/BlindReviewToggle";
const CollusionGraph = React.lazy(() => import("../components/CollusionGraph"));
import SimilarityMatrix from "../components/SimilarityMatrix";
import MatrixViewer from "../components/MatrixViewer";
import "../styles/portal.css";

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

const assignmentItemShape = PropTypes.shape({
  name: PropTypes.string,
  batch_id: PropTypes.string,
  expected_count: PropTypes.number,
  created_at: PropTypes.string,
  owner_user_id: PropTypes.string,
});

AssignmentCard.propTypes = {
  item: assignmentItemShape.isRequired,
  active: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
};
const MemoizedAssignmentCard = memo(AssignmentCard);

function buildHistogram(values, buckets = 5) {
  const counts = new Array(buckets).fill(0);
  values.forEach(v => {
    const idx = Math.min(Math.floor(v * buckets), buckets - 1);
    counts[idx]++;
  });
  return counts;
}

const BatchAnalytics = memo(function BatchAnalytics({ submissions }) {
  const scoreHist = useMemo(
    () => buildHistogram(submissions.map(s => s.plagiarism_score).filter(s => s != null)),
    [submissions]
  );
  const aiHist = useMemo(
    () => buildHistogram(submissions.map(s => s.ai_score).filter(s => s != null)),
    [submissions]
  );
  const scores = useMemo(() => submissions.map(s => s.plagiarism_score).filter(s => s != null), [submissions]);
  const aiScores = useMemo(() => submissions.map(s => s.ai_score).filter(s => s != null), [submissions]);
  const maxCount = Math.max(1, ...scoreHist, ...aiHist);

  const avgScore = scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length * 100).toFixed(1) : '—';
  const avgAi = aiScores.length ? (aiScores.reduce((a, b) => a + b, 0) / aiScores.length * 100).toFixed(1) : '—';
  const maxScore = scores.length ? (Math.max(...scores) * 100).toFixed(1) : '—';

  const bands = ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%'];
  const bandColors = ['#93c5fd', '#86efac', '#fde68a', '#fdba74', '#fca5a5'];

  return (
    <div className="batch-analytics">
      <div className="section-label">Analytics</div>
      <h3 className="section-title" style={{ fontSize: 15, margin: '4px 0 14px' }}>Batch overview</h3>
      <div className="analytics-stats">
        <div className="analytics-stat">
          <span>{submissions.length}</span>
          <small>Submissions</small>
        </div>
        <div className="analytics-stat">
          <span>{avgScore}%</span>
          <small>Avg similarity</small>
        </div>
        <div className="analytics-stat">
          <span>{maxScore}%</span>
          <small>Max similarity</small>
        </div>
        <div className="analytics-stat">
          <span>{avgAi}%</span>
          <small>Avg AI score</small>
        </div>
      </div>
      {scores.length > 0 && (
        <div className="analytics-chart">
          <div className="analytics-chart-title">Similarity distribution</div>
          <div className="analytics-bars">
            {scoreHist.map((count, i) => (
              <div key={i} className="analytics-bar-col">
                <div className="analytics-bar-wrapper">
                  <div className="analytics-bar" style={{ height: `${(count / maxCount) * 100}%`, background: bandColors[i] }} />
                </div>
                <div className="analytics-bar-label">{bands[i]}</div>
                <div className="analytics-bar-count">{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {aiScores.length > 0 && (
        <div className="analytics-chart">
          <div className="analytics-chart-title">AI detection distribution</div>
          <div className="analytics-bars">
            {aiHist.map((count, i) => (
              <div key={i} className="analytics-bar-col">
                <div className="analytics-bar-wrapper">
                  <div className="analytics-bar" style={{ height: `${(count / maxCount) * 100}%`, background: bandColors[i] }} />
                </div>
                <div className="analytics-bar-label">{bands[i]}</div>
                <div className="analytics-bar-count">{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

BatchAnalytics.propTypes = {
  submissions: PropTypes.array.isRequired,
};

const SUBMISSIONS_PAGE_SIZE = 25;

export default function Dashboard() {
  const navigate = useNavigate();
  const email = getStoredEmail();

  const assignments = useAssignments();
  const {
    token, loading, error, setError,
    ownedAssignments, sharedAssignments,
    selectedId, setSelectedId,
    selected,
    creating, assignmentName, setAssignmentName,
    expectedCount, setExpectedCount,
    renaming, setRenaming,
    saving, renameValue, setRenameValue,
    confirmDelete, setConfirmDelete,
    deleting, stats,
    createAssignment, handleRename, handleDelete,
  } = assignments;

  const details = useAssignmentDetails(token, selectedId, setError, navigate);
  const {
    submissions, matrix, matrixIds,
    refreshing, blindReview, setBlindReview,
    threshold, setThreshold,
    displayLabels, submissionCount,
    loadAssignmentDetails,
  } = details;

  const { computing, wsProgress, computeSimilarity } = useSimilarityCompute(
    token, selectedId, loadAssignmentDetails, setError
  );

  const { viewer, viewerLoading, handleCellClick, closeViewer } = useMatrixViewer(
    selectedId, matrixIds, displayLabels, submissions
  );

  const detailStats = useMemo(() => ({
    ...stats,
    submissions: submissionCount,
  }), [stats, submissionCount]);

  const [assignmentSearch, setAssignmentSearch] = useState("");
  const [submissionPage, setSubmissionPage] = useState(0);
  useEffect(() => { setSubmissionPage(0); }, [selectedId]);
  const searchLower = assignmentSearch.trim().toLowerCase();
  const filterBySearch = useCallback(
    (items) =>
      !searchLower
        ? items
        : items.filter(
            (item) =>
              (item.name || "").toLowerCase().includes(searchLower) ||
              (item.batch_id || "").toLowerCase().includes(searchLower)
          ),
    [searchLower]
  );
  const filteredOwned = useMemo(
    () => filterBySearch(ownedAssignments),
    [filterBySearch, ownedAssignments]
  );
  const filteredShared = useMemo(
    () => filterBySearch(sharedAssignments),
    [filterBySearch, sharedAssignments]
  );

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
            <span>{detailStats.total}</span>
            <small>Assignments</small>
          </div>
          <div className="dashboard-stat">
            <span>{detailStats.owned}</span>
            <small>Owned</small>
          </div>
          <div className="dashboard-stat">
            <span>{detailStats.submissions}</span>
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

      {wsProgress.failed && (
        <div className="status-box error" style={{ margin: "0 auto", maxWidth: 960, fontSize: 13 }}>
          Live updates unavailable — refresh the page manually to check progress.
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
            <input
              type="search"
              className="assignment-search"
              placeholder="Search assignments..."
              aria-label="Search assignments"
              value={assignmentSearch}
              onChange={(e) => setAssignmentSearch(e.target.value)}
            />
            <div className="list-heading">Owned</div>
            <div className="assignment-list">
              {loading
                ? Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton skeleton-card" />)
                : filteredOwned.map((item) => (
                <MemoizedAssignmentCard key={item.batch_id} item={item} active={selectedId === item.batch_id} onClick={() => setSelectedId(item.batch_id)} />
              ))}
              {!loading && filteredOwned.length === 0 && (
                <div className="empty-state">
                  <div className="empty-state-icon">+</div>
                  <div className="empty-state-title">{searchLower ? "No matches" : "No assignments yet"}</div>
                  <div className="empty-state-hint">{searchLower ? "Try a different search term." : "Create your first assignment above to start collecting submissions."}</div>
                </div>
              )}
            </div>
          </div>

          <div className="assignment-list-block">
            <div className="list-heading">Shared</div>
            <div className="assignment-list">
              {loading
                ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="skeleton skeleton-card" />)
                : filteredShared.map((item) => (
                <MemoizedAssignmentCard key={item.batch_id} item={item} active={selectedId === item.batch_id} onClick={() => setSelectedId(item.batch_id)} />
              ))}
              {!loading && filteredShared.length === 0 && (
                <div className="empty-state">
                  <div className="empty-state-hint">{searchLower ? "No matches in shared assignments." : "No shared assignments. Ask a teacher to share an access code with you."}</div>
                </div>
              )}
            </div>
          </div>
        </aside>

        <main className="dashboard-panel dashboard-panel-detail">
          <div className="detail-header">
            <div>
              <div className="section-label">Assignment detail</div>
              {renaming ? (
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") { setRenaming(false); setRenameValue(""); } }}
                    className="input"
                    style={{ fontSize: 20, fontWeight: 700, padding: "4px 8px" }}
                    autoFocus
                  />
                  <button className="button-sm button" onClick={handleRename} disabled={saving}>{saving ? "Saving..." : "Save"}</button>
                  <button className="button-sm button-secondary" onClick={() => { setRenaming(false); setRenameValue(""); }}>Cancel</button>
                </div>
              ) : (
                <h2 className="section-title">{selected?.name || "Select an assignment"}</h2>
              )}
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
              <button
                className="button-secondary"
                type="button"
                disabled={!selectedId || !submissions.length}
                onClick={async () => {
                  try {
                    const res = await fetch(`${API_BASE}/portal/export/${selectedId}`, {
                      headers: await getAuthHeaders(),
                      credentials: "include",
                    });
                    if (!res.ok) throw new Error("Export failed");
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `results_${selected?.name || selectedId}.csv`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) {
                    showToast("Failed to export CSV", "error");
                  }
                }}
                aria-label="Export batch results as CSV"
              >
                Export CSV
              </button>
              {selected && (
                <>
                  <button className="button-secondary" type="button" onClick={() => { setRenameValue(selected.name); setRenaming(true); }}>
                    Rename
                  </button>
                  <button className="button-secondary" type="button" onClick={() => setConfirmDelete(selected.name)} style={{ color: "#dc2626" }}>
                    Delete
                  </button>
                </>
              )}
            </div>
          </div>

          {confirmDelete && selected && (
            <div className="modal-overlay" onClick={() => setConfirmDelete("")} role="dialog" aria-modal="true">
              <div className="modal-panel" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 440 }}>
                <h3 style={{ margin: "0 0 8px" }}>Delete assignment?</h3>
                <p style={{ margin: "0 0 16px", color: "#64748b" }}>
                  This will permanently delete &ldquo;<strong>{selected.name}</strong>&rdquo; and all its submissions and similarity data. Type the assignment name to confirm.
                </p>
                <input
                  value={confirmDelete}
                  onChange={(e) => setConfirmDelete(e.target.value)}
                  placeholder="Type assignment name to confirm"
                  className="input"
                  style={{ width: "100%", marginBottom: 12 }}
                />
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button className="button-secondary" onClick={() => setConfirmDelete("")}>Cancel</button>
                  <button className="button" onClick={handleDelete} disabled={confirmDelete !== selected.name || deleting} style={{ background: "#dc2626", color: "#fff" }}>
                    {deleting ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {selected ? (
            <>
              {refreshing && (
                <div className="status-box" style={{ margin: "0 0 12px", padding: "6px 12px", fontSize: 13, color: "#64748b" }}>
                  Refreshing data...
                </div>
              )}
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
                {selected.due_date && (
                  <div className="detail-card">
                    <span className="detail-label">Due date</span>
                    <strong>{new Date(selected.due_date).toLocaleDateString()}</strong>
                  </div>
                )}
                <div className="detail-card">
                  <span className="detail-label">Resubmission</span>
                  <strong>{selected.allow_resubmission !== false ? 'Allowed' : 'Disabled'}</strong>
                </div>
                {selected.max_submissions > 0 && (
                  <div className="detail-card">
                    <span className="detail-label">Max submissions</span>
                    <strong>{selected.max_submissions}</strong>
                  </div>
                )}
              </div>

              <div className="submissions-table">
                {refreshing ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="skeleton-row">
                      <div className="skeleton-row-left">
                        <div className="skeleton skeleton-text" style={{ width: "30%" }} />
                        <div className="skeleton skeleton-text" style={{ width: "50%" }} />
                        <div className="skeleton skeleton-text" style={{ width: "40%" }} />
                      </div>
                      <div className="skeleton-row-right">
                        <div className="skeleton skeleton-text" style={{ width: 50, height: 16 }} />
                        <div className="skeleton skeleton-text" style={{ width: 40, height: 16 }} />
                      </div>
                    </div>
                  ))
                ) : submissions.length > 0 ? submissions
                    .slice(submissionPage * SUBMISSIONS_PAGE_SIZE, (submissionPage + 1) * SUBMISSIONS_PAGE_SIZE)
                    .map((submission, idx) => {
                  const globalIdx = submissionPage * SUBMISSIONS_PAGE_SIZE + idx;
                  const aiScore = submission.ai_score != null ? submission.ai_score : null;
                  let aiBadge = null;
                  if (aiScore != null && aiScore >= 0) {
                    const pct = (aiScore * 100).toFixed(0);
                    let cls, caveat;
                    if (aiScore > 0.7) {
                      cls = 'ai-badge-red';
                      caveat = 'Likely AI-generated';
                    } else if (aiScore > 0.3) {
                      cls = 'ai-badge-yellow';
                      caveat = 'Possibly AI-assisted';
                    } else {
                      cls = 'ai-badge-green';
                      caveat = 'Likely human-written';
                    }
                    aiBadge = <span className={`ai-badge ${cls}`} title={caveat}>{pct}%</span>;
                  }
                  const score = submission.plagiarism_score;
                  let scoreBadge = null;
                  if (score != null) {
                    const pct = (score * 100).toFixed(1);
                    const cls = score > 0.8 ? 'score-badge-red' : score > 0.6 ? 'score-badge-orange' : score > 0.4 ? 'score-badge-yellow' : score > 0.2 ? 'score-badge-green' : 'score-badge-blue';
                    scoreBadge = <span className={`score-badge ${cls}`} title={`Similarity: ${pct}%`}>{pct}%</span>;
                  }
                    const fileName = submission.original_filename || (submission.filename ? submission.filename.split("_").slice(3).join("_") : "—");
                  return (
                      <div key={submission.submission_id} className="submission-row">
                        <div>
                          <strong>{blindReview ? `Submission ${globalIdx + 1}` : submission.roll}</strong>
                          <div className="small-copy">{blindReview ? "—" : (submission.name || "Name not provided")}</div>
                          <div className="small-copy">{blindReview ? "—" : (submission.email || "Email not provided")}</div>
                          <div className="small-copy" style={{ color: "#64748b", fontSize: 12 }}>{fileName}</div>
                        </div>
                        <div className="row-meta">
                          {scoreBadge}
                          {aiBadge}
                          <span>{submission.status || "ACTIVE"}</span>
                          <span className="mono">{submission.submission_id.slice(0, 8)}</span>
                        </div>
                      </div>
                    );
                }) : (
                  <div className="empty-state">
                    <div className="empty-state-icon">📄</div>
                    <div className="empty-state-title">No submissions yet</div>
                    <div className="empty-state-hint">Share the access code with students so they can submit their work.</div>
                  </div>
                )}
                {submissions.length > SUBMISSIONS_PAGE_SIZE && (
                  <div className="submission-pagination">
                    <button
                      type="button"
                      className="button-secondary"
                      disabled={submissionPage === 0}
                      onClick={() => setSubmissionPage((p) => Math.max(0, p - 1))}
                    >
                      ← Prev
                    </button>
                    <span>
                      Page {submissionPage + 1} of {Math.ceil(submissions.length / SUBMISSIONS_PAGE_SIZE)}
                    </span>
                    <button
                      type="button"
                      className="button-secondary"
                      disabled={(submissionPage + 1) * SUBMISSIONS_PAGE_SIZE >= submissions.length}
                      onClick={() => setSubmissionPage((p) => p + 1)}
                    >
                      Next →
                    </button>
                  </div>
                )}
              </div>

              <div className="matrix-card matrix-card-compact">
                <div className="section-label">Similarity matrix</div>
                {matrix && matrix.length > 0 && (
                  <div className="threshold-filter">
                    <label className="threshold-label">
                      Threshold: <strong>{(threshold * 100).toFixed(0)}%</strong>
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="0.8"
                      step="0.05"
                      value={threshold}
                      onChange={(e) => setThreshold(parseFloat(e.target.value))}
                      className="threshold-slider"
                    />
                    {threshold > 0 && (
                      <button
                        className="button-secondary button-sm"
                        type="button"
                        onClick={() => setThreshold(0)}
                      >
                        Reset
                      </button>
                    )}
                  </div>
                )}
                {refreshing && !matrix ? (
                  <div className="skeleton skeleton-matrix" />
                ) : (
                  <SimilarityMatrix matrix={matrix} labels={displayLabels} onCellClick={handleCellClick} threshold={threshold} />
                )}
              </div>

              {matrix && displayLabels && matrix.length === displayLabels.length && matrix.length >= 3 && (
                <Suspense fallback={<div style={{ padding: 20, textAlign: "center" }}>Loading graph...</div>}>
                  <CollusionGraph matrix={matrix} labels={displayLabels} />
                </Suspense>
              )}

              {submissions.length > 0 && (
                <BatchAnalytics submissions={submissions} />
              )}
            </>
          ) : (
            <div className="empty-state empty-state-large">
              <div className="empty-state-icon">📊</div>
              <div className="empty-state-title">Select an assignment</div>
              <div className="empty-state-hint">Choose an assignment from the left panel to view submissions, similarity matrix, and details.</div>
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
        loading={viewerLoading}
        onClose={closeViewer}
      />
    </div>
  );
}
