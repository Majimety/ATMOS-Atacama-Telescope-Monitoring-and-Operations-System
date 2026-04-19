import { useEffect, useRef } from "react";

export function useWebSocket(url, onMessage) {
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);

  // เก็บ callback ล่าสุดไว้ใน ref เพื่อไม่ให้ useEffect re-run ทุกครั้งที่ render
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    let reconnectTimer = null;
    let alive = true;

    function connect() {
      if (!alive) return;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try { onMessageRef.current(JSON.parse(event.data)); } catch {}
      };

      ws.onerror = () => {
        // onerror จะตามด้วย onclose เสมอ ไม่ต้อง reconnect ตรงนี้
        // log ไว้ให้รู้ว่า connection มีปัญหาโดยไม่ต้อง throw
        console.warn("[ATMOS] WebSocket error — will reconnect");
      };

      ws.onclose = () => {
        if (alive) reconnectTimer = setTimeout(connect, 2000);
      };
    }

    connect();

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [url]);

  function send(cmd) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }

  return { send };
}