import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE } from "../utils/config";
import { clearToken, getAuthHeaders, getToken, isTokenExpired } from "../utils/auth";

export default function useAssignments() {
  const navigate = useNavigate();
  const token = getToken();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ownedAssignments, setOwnedAssignments] = useState([]);
  const [sharedAssignments, setSharedAssignments] = useState([]);
  const [selectedId, setSelectedId] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("batch") || "";
  });
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [assignmentName, setAssignmentName] = useState("");
  const [expectedCount, setExpectedCount] = useState(30);
  const [renaming, setRenaming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");
  const [deleting, setDeleting] = useState(false);

  const stats = useMemo(() => {
    const total = ownedAssignments.length + sharedAssignments.length;
    return { total, owned: ownedAssignments.length, shared: sharedAssignments.length };
  }, [ownedAssignments, sharedAssignments]);

  const loadAssignments = useCallback(async () => {
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
  }, [token, navigate]);

  const createAssignment = useCallback(async (event, { due_date } = {}) => {
    event.preventDefault();
    if (!token) return navigate("/auth");
    setCreating(true);
    setError("");
    try {
      const headers = { "Content-Type": "application/json", ...(await getAuthHeaders()) };
      const response = await fetch(`${API_BASE}/portal/assignments`, {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({ name: assignmentName, expected_count: Number(expectedCount) || 0, due_date: due_date || null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to create assignment");
      setAssignmentName("");
      await loadAssignments();
      setSelectedId(data.batch_id);
      return data.batch_id;
    } catch (error) {
      setError(error.message);
      return null;
    } finally {
      setCreating(false);
    }
  }, [token, navigate, assignmentName, expectedCount, loadAssignments]);

  const handleRename = useCallback(async () => {
    if (!selectedId || !renameValue.trim()) return;
    const newName = renameValue.trim();
    const originalName = selected?.name || "";
    setSaving(true);
    setError("");
    setSelected((s) => (s ? { ...s, name: newName } : s));
    setOwnedAssignments((prev) => prev.map((a) => a.batch_id === selectedId ? { ...a, name: newName } : a));
    setSharedAssignments((prev) => prev.map((a) => a.batch_id === selectedId ? { ...a, name: newName } : a));
    try {
      const res = await fetch(`${API_BASE}/portal/assignments/${selectedId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(await getAuthHeaders()) },
        credentials: "include",
        body: JSON.stringify({ name: newName }),
      });
      if (res.status === 401) { clearToken(); navigate("/auth"); return; }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to rename");
      }
      setSaving(false);
      setRenaming(false);
      setRenameValue("");
    } catch (e) {
      setSelected((s) => (s ? { ...s, name: originalName } : s));
      setOwnedAssignments((prev) => prev.map((a) => a.batch_id === selectedId ? { ...a, name: originalName } : a));
      setSharedAssignments((prev) => prev.map((a) => a.batch_id === selectedId ? { ...a, name: originalName } : a));
      setError(e.message);
      setSaving(false);
    }
  }, [selectedId, renameValue, selected, navigate]);

  const handleDelete = useCallback(async () => {
    if (!selectedId || confirmDelete !== selected?.name) return;
    setDeleting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/portal/assignments/${selectedId}`, {
        method: "DELETE",
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      if (res.status === 401) { clearToken(); navigate("/auth"); return; }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to delete");
      }
      setConfirmDelete("");
      setDeleting(false);
      setSelectedId("");
      setSelected(null);
      await loadAssignments();
    } catch (e) {
      setError(e.message);
      setDeleting(false);
    }
  }, [selectedId, confirmDelete, selected, navigate, loadAssignments]);

  useEffect(() => {
    if (!token) { navigate("/auth"); return; }
    if (isTokenExpired(token)) { clearToken(); navigate("/auth"); return; }
    loadAssignments();
  }, [token, navigate, loadAssignments]);

  return {
    token,
    loading,
    error,
    setError,
    ownedAssignments,
    sharedAssignments,
    selectedId,
    setSelectedId,
    selected,
    setSelected,
    creating,
    assignmentName,
    setAssignmentName,
    expectedCount,
    setExpectedCount,
    renaming,
    setRenaming,
    saving,
    renameValue,
    setRenameValue,
    confirmDelete,
    setConfirmDelete,
    deleting,
    stats,
    loadAssignments,
    createAssignment,
    handleRename,
    handleDelete,
  };
}
