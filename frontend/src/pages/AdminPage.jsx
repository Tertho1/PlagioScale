import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getAuthHeaders, fetchMe, clearToken } from "../utils/auth";
import { showToast } from "../components/Toast";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function AdminPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState("stats");
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [auditLogs, setAuditLogs] = useState([]);
  const auditRef = useRef(null);
  const perPage = 20;

  useEffect(() => {
    (async () => {
      const me = await fetchMe();
      if (!me || me.role !== "admin") {
        showToast("Admin access required", "error");
        navigate("/dashboard");
        return;
      }
      setUser(me);
      setLoading(false);
      loadStats();
      loadUsers();
    })();
  }, []);

  useEffect(() => {
    if (tab === "users") loadUsers();
  }, [page, search, tab]);

  useEffect(() => {
    if (tab !== "audit") return;
    let evtSource = null;
    (async () => {
      const headers = await getAuthHeaders();
      const token = headers["Authorization"]?.split(" ")[1] || "";
      evtSource = new EventSource(`${API_BASE}/admin/audit/tail?token=${token}`);
      evtSource.onmessage = (e) => {
        setAuditLogs((prev) => {
          const next = [...prev, e.data];
          return next.length > 200 ? next.slice(-200) : next;
        });
      };
      evtSource.onerror = () => {};
    })();
    return () => { if (evtSource) evtSource.close(); };
  }, [tab]);

  useEffect(() => {
    if (auditRef.current) {
      auditRef.current.scrollTop = auditRef.current.scrollHeight;
    }
  }, [auditLogs]);

  async function loadStats() {
    try {
      const res = await fetch(`${API_BASE}/admin/stats`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) setStats(await res.json());
    } catch (e) { /* ignore fetch error */ }
  }

  async function loadUsers() {
    try {
      const params = new URLSearchParams({ page, per_page: perPage });
      if (search) params.set("search", search);
      const res = await fetch(`${API_BASE}/admin/users?${params}`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users || []);
        setTotalUsers(data.total || 0);
      }
    } catch (e) { /* ignore fetch error */ }
  }

  function handleSearch(val) {
    setSearch(val);
    setPage(1);
  }

  async function exportCsv() {
    try {
      const res = await fetch(`${API_BASE}/admin/stats/export`, {
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "plagioscale_stats.csv";
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) { /* ignore fetch error */ }
  }

  async function updateRole(userId, newRole) {
    try {
      const res = await fetch(`${API_BASE}/admin/users/${userId}/role`, {
        method: "POST",
        headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ role: newRole }),
      });
      if (res.ok) {
        showToast(`Role updated to ${newRole}`, "success");
        loadUsers();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || "Failed to update role", "error");
      }
    } catch {
      showToast("Network error", "error");
    }
  }

  async function sendNotifications() {
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/admin/notifications/send`, {
        method: "POST",
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Sent ${data.sent}/${data.pending} notifications`, "success");
        loadStats();
      }
    } catch {
      showToast("Failed to send notifications", "error");
    }
    setSending(false);
  }

  if (loading) {
    return <div className="page-shell"><div className="loading-spinner" /></div>;
  }

  const totalPages = Math.ceil(totalUsers / perPage);

  return (
    <div className="page-shell">
      <div className="hero">
        <h1>Admin Panel</h1>
        <p>{user?.email}</p>
      </div>

      <div style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {["stats", "users", "notifications", "audit"].map((t) => (
          <button key={t} className="btn" onClick={() => setTab(t)} style={{ opacity: tab === t ? 1 : 0.6 }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <button className="btn" onClick={() => { clearToken(); navigate("/"); }} style={{ marginLeft: "auto" }}>
          Logout
        </button>
      </div>

      {tab === "stats" && stats && (
        <div className="card">
          <h3>System Statistics</h3>
          <table>
            <tbody>
              {Object.entries(stats).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ fontWeight: 600, padding: "6px 12px" }}>{k.replace(/_/g, " ")}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button className="btn" onClick={loadStats}>Refresh</button>
            <button className="btn" onClick={exportCsv}>Export CSV</button>
          </div>
        </div>
      )}

      {tab === "users" && (
        <div className="card">
          <h3>Users ({totalUsers})</h3>
          <input
            type="text"
            placeholder="Search by email or name..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            style={{ width: "100%", maxWidth: 320, padding: "6px 10px", marginBottom: 12, boxSizing: "border-box" }}
            aria-label="Search users"
          />
          <table className="matrix-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id}>
                  <td>{u.email}</td>
                  <td>{u.name || "—"}</td>
                  <td><span className={`badge badge-${u.role}`}>{u.role}</span></td>
                  <td>
                    <select
                      value={u.role}
                      onChange={(e) => updateRole(u.user_id, e.target.value)}
                      style={{ padding: "4px 8px" }}
                    >
                      <option value="user">user</option>
                      <option value="teacher">teacher</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div style={{ marginTop: 12, display: "flex", gap: 8, justifyContent: "center" }}>
              <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Previous</button>
              <span style={{ padding: "6px 12px" }}>Page {page} of {totalPages}</span>
              <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          )}
        </div>
      )}

      {tab === "notifications" && (
        <div className="card">
          <h3>Email Notifications</h3>
          {stats && (
            <p>{stats.pending_notifications} pending notifications</p>
          )}
          <button className="btn" onClick={sendNotifications} disabled={sending}>
            {sending ? "Sending..." : "Send Pending Notifications"}
          </button>
        </div>
      )}

      {tab === "audit" && (
        <div className="card">
          <h3>Live Audit Log</h3>
          <div ref={auditRef} style={{ maxHeight: 500, overflowY: "auto", fontFamily: "monospace", fontSize: 12, background: "var(--surface-muted)", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
            {auditLogs.length === 0 && <span style={{ color: "var(--text-soft)" }}>Waiting for audit events...</span>}
            {auditLogs.map((entry, i) => (
              <div key={i} style={{ padding: "2px 0", borderBottom: "1px solid var(--border)" }}>{entry}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
