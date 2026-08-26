import { useCallback, useState } from "react";
import { API_BASE } from "../utils/config";
import { getAuthHeaders } from "../utils/auth";
import { showToast } from "../components/Toast";

export default function useMatrixViewer(selectedId, matrixIds, displayLabels, submissions) {
  const [viewer, setViewer] = useState({ open: false, left: null, right: null, similarity: 0 });
  const [viewerLoading, setViewerLoading] = useState(false);

  const handleCellClick = useCallback(async (rowIdx, colIdx, cellValue) => {
    const leftId = matrixIds?.[rowIdx];
    const rightId = matrixIds?.[colIdx];
    if (!leftId || !rightId) return;
    const leftLabel = displayLabels[rowIdx];
    const rightLabel = displayLabels[colIdx];

    const leftSub = submissions.find(s => s.submission_id === leftId);
    const rightSub = submissions.find(s => s.submission_id === rightId);

    setViewerLoading(true);
    async function fetchText(subId) {
      try {
        const res = await fetch(
          `${API_BASE}/portal/submissions/${selectedId}/${subId}/text`,
          { headers: await getAuthHeaders(), credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          return { text: data.text || "", roll: data.roll || "" };
        }
      } catch (e) { console.warn("Failed to fetch submission text:", e); showToast("Failed to load submission text", "error"); }
      return { text: "", roll: "" };
    }

    const leftResult = leftId ? await fetchText(leftId) : { text: "", roll: "" };
    const rightResult = rightId ? await fetchText(rightId) : { text: "", roll: "" };

    setViewerLoading(false);
    setViewer({
      open: true,
      left: {
        submission_id: leftId,
        label: leftLabel,
        text: leftResult.text,
        roll: leftSub?.roll || leftResult.roll,
        name: leftSub?.name || "",
        filename: leftSub?.filename || "",
      },
      right: {
        submission_id: rightId,
        label: rightLabel,
        text: rightResult.text,
        roll: rightSub?.roll || rightResult.roll,
        name: rightSub?.name || "",
        filename: rightSub?.filename || "",
      },
      similarity: cellValue,
    });
  }, [matrixIds, displayLabels, selectedId, submissions]);

  const closeViewer = useCallback(() => {
    setViewer((v) => ({ ...v, open: false }));
  }, []);

  return {
    viewer,
    setViewer,
    viewerLoading,
    handleCellClick,
    closeViewer,
  };
}
