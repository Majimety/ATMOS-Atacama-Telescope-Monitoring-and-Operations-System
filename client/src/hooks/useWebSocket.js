import { useEffect, useRef } from "react";

const RECONNECT_BASE_MS  = 1_000;
const RECONNECT_MAX_MS   = 30_000;
const RECONNECT_JITTER   = 500;

export function useWebSocket(url, onMessage) {
  const wsRef     = useRef(null);
  const aliveRef  = useRef(true);
  const attemptRef = useRef(0);
  const timerRef  = useRef(null);
  const onMsgRef  = useRef(onMessage);

  // เก็บ callback ล่าสุดไว้ใน ref — ไม่ให้ useEffect re-run ทุก render
  useEffect(() => { onMsgRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    aliveRef.current  = true;
    attemptRef.current = 0;

    function connect() {
      if (!aliveRef.current) return;

      let ws;
      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        try { onMsgRef.current(JSON.parse(ev.data)); } catch {}
      };

      ws.onopen = () => {
        attemptRef.current = 0; // reset backoff on successful connection
      };

      ws.onerror = () => {
        // onerror จะตามด้วย onclose เสมอ — reconnect ใน onclose
      };

      ws.onclose = () => {
        if (aliveRef.current) scheduleReconnect();
      };
    }

    function scheduleReconnect() {
      const jitter  = Math.random() * RECONNECT_JITTER;
      const delay   = Math.min(
        RECONNECT_BASE_MS * Math.pow(2, attemptRef.current) + jitter,
        RECONNECT_MAX_MS,
      );
      attemptRef.current++;
      timerRef.current = setTimeout(connect, delay);
    }

    connect();

    return () => {
      aliveRef.current = false;
      clearTimeout(timerRef.current);
      wsRef.current?.close(1000, "component unmount");
    };
  }, [url]); // reconnect ใหม่ถ้า url เปลี่ยน (เช่น token refresh)

  function send(cmd) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
      return true;
    }
    return false;
  }

  return { send };
}
