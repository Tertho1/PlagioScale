import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../utils/config";
import { getAuthHeaders } from "../utils/auth";
import { useBatchProgress } from "../utils/websocket";

export default function useSimilarityCompute(token, selectedId, loadAssignmentDetails, setError) {
  const [computing, setComputing] = useState(false);
  const wsProgress = useBatchProgress(selectedId);
  const abortRef = useRef(null);

  useEffect(() => {
    return () => { if (abortRef.current) abortRef.current.abort(); };
  }, []);

  useEffect(() => {
    if (wsProgress.processed > 0 && selectedId) {
      loadAssignmentDetails(selectedId);
    }
  }, [wsProgress.processed, wsProgress.total, wsProgress.done, selectedId, loadAssignmentDetails]);

  const computeSimilarity = useCallback(async () => {
    if (!selectedId) return;
    setError("");
    setComputing(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await fetch(`${API_BASE}/portal/compute-similarity/${selectedId}`, {
        method: "POST",
        headers: await getAuthHeaders(),
        credentials: "include",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(data.detail || "Failed to queue compute");
        setComputing(false);
        return;
      }
      const jobId = data.job_id;
      let status = null;
      let jobError = null;
      for (let i = 0; i < 300; i++) {
        if (controller.signal.aborted) return;
        const pollInterval = wsProgress.connected ? 4000 : 2000;
        try {
          const sres = await fetch(`${API_BASE}/status/${jobId}`, { credentials: "include" });
          if (sres.ok) {
            const sjson = await sres.json();
            status = sjson.status;
            jobError = sjson.error || null;
            if (status === "COMPLETED" || status === "FAILED") break;
          }
        } catch (e) { console.warn("Poll error:", e); }
        await new Promise((r) => setTimeout(r, pollInterval));
      }
      if (status !== "COMPLETED") {
        setError(jobError || "Compute failed or timed out");
        setComputing(false);
        return;
      }
      await loadAssignmentDetails(selectedId);
    } catch (e) {
      setError(e?.message || "Compute failed");
    } finally {
      abortRef.current = null;
      setComputing(false);
    }
  }, [selectedId, loadAssignmentDetails, setError, wsProgress.connected]);

  return {
    computing,
    wsProgress,
    computeSimilarity,
  };
}
