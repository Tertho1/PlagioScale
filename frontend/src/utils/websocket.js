import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const MAX_RECONNECT_DELAY = 60000;
const BASE_RECONNECT_DELAY = 2000;

export function useBatchProgress(batchId) {
  const [progress, setProgress] = useState({ processed: 0, total: 0 });
  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const cancelledRef = useRef(false);

  const connect = useCallback(() => {
    if (!batchId || cancelledRef.current) return;

    try {
      const token = getToken();
      const wsUrl = API_BASE.replace("http", "ws") + `/portal/ws/${batchId}`;
      const ws = new WebSocket(token ? `${wsUrl}?token=${token}` : wsUrl);

      ws.onmessage = (ev) => {
        if (cancelledRef.current) return;
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
        if (!cancelledRef.current) setProgress((p) => ({ ...p, error: true }));
      };

      ws.onclose = () => {
        if (cancelledRef.current) return;
        const delay = Math.min(
          BASE_RECONNECT_DELAY * Math.pow(2, retryRef.current),
          MAX_RECONNECT_DELAY,
        );
        retryRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onopen = () => {
        retryRef.current = 0;
      };

      wsRef.current = ws;
    } catch {
      if (!cancelledRef.current) setProgress((p) => ({ ...p, error: true }));
    }
  }, [batchId]);

  useEffect(() => {
    cancelledRef.current = false;
    retryRef.current = 0;

    connect();

    return () => {
      cancelledRef.current = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return progress;
}
