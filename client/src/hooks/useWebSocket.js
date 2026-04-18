import { useEffect, useRef } from "react";

export function useWebSocket(url, onMessage) {
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);

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
