import { useState, useEffect } from "react";
import { getAuthHeaders } from "../utils/auth";
import { showToast } from "../components/Toast";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function CrossBatchPage() {
  const [assignments, setAssignments] = useState([]);
  const [batch1, setBatch1] = useState("");
  const [batch2, setBatch2] = useState("");
  const [comparisons, setComparisons] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/portal/assignments`, {
          headers: await getAuthHeaders(),
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setAssignments([...(data.owned || []), ...(data.shared || [])]);
        }
      } catch (e) { /* ignore fetch error */ }
    })();
  }, []);

  async function loadComparison() {
    if (!batch1 || !batch2) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/portal/cross-batch/${batch1}/${batch2}`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setComparisons(data.comparisons || []);
        if (!data.comparisons?.length) showToast("No cross-batch similarities found", "info");
      } else {
        showToast("Failed to load comparison", "error");
      }
    } catch {
      showToast("Network error", "error");
    }
    setLoading(false);
  }

  return (
    <div className="page-shell">
      <div className="hero">
        <h1>Cross-Batch Comparison</h1>
        <p>Compare submissions across two different assignments</p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>Batch 1</label>
            <select value={batch1} onChange={(e) => setBatch1(e.target.value)} style={{ padding: "8px 12px" }}>
              <option value="">Select...</option>
              {assignments.map((a) => (
                <option key={a.batch_id} value={a.batch_id}>{a.name} ({a.batch_id?.slice(0, 8)})</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>Batch 2</label>
            <select value={batch2} onChange={(e) => setBatch2(e.target.value)} style={{ padding: "8px 12px" }}>
              <option value="">Select...</option>
              {assignments.map((a) => (
                <option key={a.batch_id} value={a.batch_id}>{a.name} ({a.batch_id?.slice(0, 8)})</option>
              ))}
            </select>
          </div>
          <button className="btn" onClick={loadComparison} disabled={loading || !batch1 || !batch2}>
            {loading ? "Loading..." : "Compare"}
          </button>
        </div>
      </div>

      {comparisons.length > 0 && (
        <div className="card">
          <h3>Results ({comparisons.length})</h3>
          <table className="matrix-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Batch 1 Roll</th>
                <th>Batch 1 Name</th>
                <th>Batch 2 Roll</th>
                <th>Batch 2 Name</th>
                <th>Similarity</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((c, i) => (
                <tr key={i}>
                  <td>{c.roll_1}</td>
                  <td>{c.name_1 || "—"}</td>
                  <td>{c.roll_2}</td>
                  <td>{c.name_2 || "—"}</td>
                  <td><span className={`badge badge-${c.similarity_score > 0.5 ? "high" : c.similarity_score > 0.3 ? "medium" : "low"}`}>
                    {(c.similarity_score * 100).toFixed(1)}%
                  </span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
