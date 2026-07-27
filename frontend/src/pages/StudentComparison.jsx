import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getAuthHeaders } from "../utils/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function StudentComparison() {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/portal/student-comparison/${submissionId}`, {
          headers: await getAuthHeaders(),
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setDetails(data);
        }
      } catch {}
      setLoading(false);
    })();
  }, [submissionId]);

  if (loading) {
    return <div className="page-shell"><div className="loading-spinner" /></div>;
  }

  if (!details) {
    return (
      <div className="page-shell">
        <div className="hero"><h1>Comparison Details</h1></div>
        <p>Could not load comparison data.</p>
        <button className="btn" onClick={() => navigate(-1)}>Back</button>
      </div>
    );
  }

  const comparisons = details.comparisons || [];

  return (
    <div className="page-shell">
      <div className="hero">
        <h1>Comparison Details</h1>
        <p>Submission: {details.submission_id?.slice(0, 12)}...</p>
      </div>

      {comparisons.length === 0 ? (
        <div className="card"><p>No comparisons found for this submission.</p></div>
      ) : (
        <div className="card">
          <div style={{ marginBottom: 12 }}>
            <strong>Your Score:</strong>{" "}
            <span className={`badge badge-${comparisons[0]?.plagiarism_score > 0.5 ? "high" : "medium"}`}>
              {comparisons[0]?.plagiarism_score != null ? `${(comparisons[0].plagiarism_score * 100).toFixed(1)}%` : "—"}
            </span>
          </div>
          <table className="matrix-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Compared With</th>
                <th>Roll</th>
                <th>Similarity</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((c, i) => (
                <tr key={i}>
                  <td>{c.compared_with_name || "—"}</td>
                  <td>{c.compared_with_roll}</td>
                  <td>
                    <span className={`badge badge-${c.similarity_score > 0.5 ? "high" : c.similarity_score > 0.3 ? "medium" : "low"}`}>
                      {(c.similarity_score * 100).toFixed(1)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button className="btn" onClick={() => navigate(-1)} style={{ marginTop: 12 }}>Back</button>
    </div>
  );
}
