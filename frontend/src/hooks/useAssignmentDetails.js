import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE } from "../utils/config";
import { clearToken, getAuthHeaders } from "../utils/auth";

export default function useAssignmentDetails(token, selectedId, setError, navigate) {
  const [selected, setSelected] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [matrix, setMatrix] = useState(null);
  const [matrixIds, setMatrixIds] = useState([]);
  const [labels, setLabels] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [blindReview, setBlindReview] = useState(false);
  const [threshold, setThreshold] = useState(0);

  const displayLabels = useMemo(() => {
    if (!blindReview || !labels.length) return labels;
    return labels.map((_, idx) => `Submission ${idx + 1}`);
  }, [blindReview, labels]);

  const submissionCount = submissions.length;

  const loadAssignmentDetails = useCallback(async (batchId) => {
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
        setMatrixIds(ids);
        setMatrix(ids.length ? ids.map((i) => ids.map((j) => matrixObj[i][j] || 0)) : null);

        const sfetch = await fetch(`${API_BASE}/portal/submissions/${batchId}?limit=500&offset=0`, { headers: await getAuthHeaders(), credentials: "include" });
        let labelsMap = {};
        if (sfetch.ok) {
          const sjson = await sfetch.json();
          (sjson.submissions || []).forEach((submission) => {
            labelsMap[submission.submission_id] = submission.roll || submission.submission_id;
          });
        }
        setLabels(ids.map((id) => labelsMap[id] || id));
      } else {
        setMatrix(null);
        setLabels([]);
      }
    } catch (error) {
      setError(error.message);
      if (error.message?.includes("authorization") || error.message?.includes("token") || error.message?.includes("401")) {
        clearToken();
        navigate("/auth");
      }
    } finally {
      setRefreshing(false);
    }
  }, [token, setError, navigate]);

  useEffect(() => {
    if (!selectedId) return;
    const params = new URLSearchParams(window.location.search);
    const currentBatch = params.get("batch");
    if (currentBatch !== selectedId) {
      window.history.replaceState({}, "", `?batch=${selectedId}`);
    }
    loadAssignmentDetails(selectedId);
  }, [selectedId, loadAssignmentDetails]);

  return {
    selected,
    setSelected,
    submissions,
    setSubmissions,
    matrix,
    setMatrix,
    matrixIds,
    setMatrixIds,
    labels,
    setLabels,
    refreshing,
    blindReview,
    setBlindReview,
    threshold,
    setThreshold,
    displayLabels,
    submissionCount,
    loadAssignmentDetails,
  };
}
