import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function useBatchProgress(batchId) {
  const [progress, setProgress] = useState({ processed: 0, total: 0 });
  const wsRef = useRef(null);

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;

    try {
      const ws = new WebSocket(
        API_BASE.replace("http", "ws") + `/portal/ws/${batchId}`,
      );

      ws.onmessage = (ev) => {
        if (cancelled) return;
        try {
          const d = JSON.parse(ev.data);
          if (typeof d.processed === "number") {
            setProgress(d);
          }
        } catch {
          // ignore non-JSON messages (e.g. pings)
        }
      };

      ws.onerror = () => {
        if (!cancelled) setProgress((p) => ({ ...p, error: true }));
      };

      wsRef.current = ws;
    } catch {
      setProgress((p) => ({ ...p, error: true }));
    }

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [batchId]);

  return progress;
}
