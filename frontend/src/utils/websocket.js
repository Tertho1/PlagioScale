import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "./config";
import { getToken } from "./auth";
const MAX_RECONNECT_DELAY = 60000;
const BASE_RECONNECT_DELAY = 2000;
const MAX_RETRIES = 10;

export function useBatchProgress(batchId) {
  const [progress, setProgress] = useState({ processed: 0, total: 0, connected: false, failed: false });
  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const cancelledRef = useRef(false);

  const connect = useCallback(() => {
    if (!batchId || cancelledRef.current) return;
    if (retryRef.current >= MAX_RETRIES) {
      setProgress((p) => ({ ...p, failed: true }));
      return;
    }

    try {
      const token = getToken();
      const wsUrl = API_BASE.replace("http", "ws") + `/portal/ws/${batchId}`;
      const ws = new WebSocket(token ? `${wsUrl}?token=${token}` : wsUrl);

      ws.onmessage = (ev) => {
        if (cancelledRef.current) return;
        try {
          const d = JSON.parse(ev.data);
          if (typeof d.processed === "number") {
            setProgress((p) => ({ ...p, processed: d.processed, total: d.total, connected: true, failed: false }));
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
        setProgress((p) => ({ ...p, connected: false }));
        const delay = Math.min(
          BASE_RECONNECT_DELAY * Math.pow(2, retryRef.current),
          MAX_RECONNECT_DELAY,
        );
        retryRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onopen = () => {
        retryRef.current = 0;
        setProgress((p) => ({ ...p, connected: true, failed: false }));
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
