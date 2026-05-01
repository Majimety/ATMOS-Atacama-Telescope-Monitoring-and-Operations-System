/**
 * resilientWS.js  —  Production WebSocket client for ATMOS telemetry
 */

import { create } from "zustand";
import { useAuthStore } from "./auth";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 60_000;
const RECONNECT_JITTER_MS = 500;
const HEARTBEAT_INTERVAL_MS = 10_000;
const HEARTBEAT_TIMEOUT_MS = 5_000;
const BUFFER_MAX_FRAMES = 500;
const GAP_THRESHOLD_MS = 3_000;
const NETWORK_WINDOW = 20;

const DB_NAME = "atmos-telemetry-buffer";
const STORE_NAME = "frames";

async function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "seq" });
        store.createIndex("ts", "ts", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function bufferFrame(db, frame) {
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    store.put(frame);
    const countReq = store.count();
    countReq.onsuccess = () => {
      if (countReq.result > BUFFER_MAX_FRAMES) {
        const cursor = store.openCursor();
        cursor.onsuccess = (e) => e.target.result?.delete();
      }
    };
    tx.oncomplete = resolve;
  });
}

async function drainBuffer(db, onFrame) {
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const req = store.openCursor();
    req.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        onFrame(cursor.value);
        cursor.delete();
        cursor.continue();
      } else {
        resolve();
      }
    };
  });
}

export const useResilientWSStore = create((set) => ({
  status: "disconnected",
  reconnectAttempt: 0,
  nextReconnectIn: null,
  lastConnectedAt: null,
  lastFrameAt: null,
  latencyMs: null,
  jitterMs: null,
  frameRate: null,
  networkScore: null,
  gaps: [],
  bufferedFrames: 0,
  telemetry: null,

  _setStatus: (status, extra = {}) => set({ status, ...extra }),
  _setTelemetry: (data) => set({ telemetry: data, lastFrameAt: Date.now() }),
  _addGap: (gap) => set((s) => ({ gaps: [gap, ...s.gaps].slice(0, 50) })),
  _setQuality: (q) => set(q),
  _setBuffered: (n) => set({ bufferedFrames: n }),
}));

export class ResilientWebSocket {
  constructor(urlFactory, options = {}) {
    this.urlFactory = urlFactory;
    this.opts = { bufferOffline: true, ...options };

    this.ws = null;
    this.db = null;
    this.reconnectAttempt = 0;
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.heartbeatTimeoutTimer = null;
    this.lastFrameTs = null;
    this.frameTimestamps = [];
    this.latencySamples = [];
    this._pingTs = null;
    this._active = false;
  }

  async connect() {
    this._active = true;
    if (this.opts.bufferOffline) {
      this.db = await openDB().catch(() => null);
    }
    this._doConnect();
  }

  disconnect() {
    this._active = false;
    this._clearTimers();
    this.ws?.close(1000, "client disconnect");
    this.ws = null;
    useResilientWSStore.getState()._setStatus("disconnected");
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
      return true;
    }
    return false;
  }

  _doConnect() {
    if (!this._active) return;
    const url = this.urlFactory();

    useResilientWSStore.getState()._setStatus(
      this.reconnectAttempt === 0 ? "connecting" : "reconnecting",
      { reconnectAttempt: this.reconnectAttempt }
    );

    try {
      this.ws = new WebSocket(url);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => this._onOpen();
    this.ws.onmessage = (ev) => this._onMessage(ev);
    this.ws.onclose = () => this._onClose();
    this.ws.onerror = () => {};
  }

  async _onOpen() {
    this.reconnectAttempt = 0;
    this._clearTimers();

    useResilientWSStore.getState()._setStatus("connected", {
      lastConnectedAt: Date.now(),
      reconnectAttempt: 0,
      nextReconnectIn: null,
    });

    if (this.db) {
      let count = 0;
      await drainBuffer(this.db, (frame) => {
        this._processFrame(frame, true);
        count++;
      });
      if (count) console.log(`[ATMOS WS] Replayed ${count} buffered frames`);
      useResilientWSStore.getState()._setBuffered(0);
    }

    this._startHeartbeat();
  }

  async _onMessage(ev) {
    const now = Date.now();

    if (ev.data === "pong") {
      clearTimeout(this.heartbeatTimeoutTimer);
      const latency = now - this._pingTs;
      this._recordLatency(latency);
      return;
    }

    let frame;
    try {
      frame = JSON.parse(ev.data);
    } catch {
      return;
    }

    if (this.lastFrameTs) {
      const gap = now - this.lastFrameTs;
      if (gap > GAP_THRESHOLD_MS) {
        useResilientWSStore.getState()._addGap({
          start: this.lastFrameTs,
          end: now,
          durationMs: gap,
        });
        console.warn(`[ATMOS WS] Data gap: ${(gap / 1000).toFixed(1)}s`);
      }
    }
    this.lastFrameTs = now;

    this.frameTimestamps.push(now);
    if (this.frameTimestamps.length > 30) this.frameTimestamps.shift();
    const fps = this._calcFPS();

    this._processFrame(frame);
    useResilientWSStore.getState()._setQuality({ frameRate: fps });
  }

  _processFrame(frame, isBuffered = false) {
    if (this.opts.onMessage) this.opts.onMessage(frame, isBuffered);
    useResilientWSStore.getState()._setTelemetry(frame);
  }

  _onClose() {
    this._clearTimers();
    if (!this._active) return;
    useResilientWSStore.getState()._setStatus("reconnecting");
    this._scheduleReconnect();
  }

  _scheduleReconnect() {
    this._clearTimers();
    const jitter = Math.random() * RECONNECT_JITTER_MS;
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, this.reconnectAttempt) + jitter,
      RECONNECT_MAX_MS
    );
    this.reconnectAttempt++;

    useResilientWSStore.getState()._setStatus("reconnecting", {
      nextReconnectIn: Math.round(delay / 1000),
      reconnectAttempt: this.reconnectAttempt,
    });

    let remaining = Math.round(delay / 1000);
    const countdown = setInterval(() => {
      remaining--;
      if (remaining > 0) {
        useResilientWSStore.getState()._setStatus("reconnecting", {
          nextReconnectIn: remaining,
        });
      }
    }, 1000);

    this.reconnectTimer = setTimeout(() => {
      clearInterval(countdown);
      this._doConnect();
    }, delay);
  }

  _startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState !== WebSocket.OPEN) return;
      this._pingTs = Date.now();
      this.ws.send("ping");
      this.heartbeatTimeoutTimer = setTimeout(() => {
        console.warn("[ATMOS WS] Heartbeat timeout — forcing reconnect");
        this.ws.close();
      }, HEARTBEAT_TIMEOUT_MS);
    }, HEARTBEAT_INTERVAL_MS);
  }

  _clearTimers() {
    clearTimeout(this.reconnectTimer);
    clearInterval(this.heartbeatTimer);
    clearTimeout(this.heartbeatTimeoutTimer);
  }

  _recordLatency(ms) {
    this.latencySamples.push(ms);
    if (this.latencySamples.length > NETWORK_WINDOW) this.latencySamples.shift();
    const avg = this.latencySamples.reduce((a, b) => a + b, 0) / this.latencySamples.length;
    const jitter = Math.sqrt(
      this.latencySamples.reduce((s, v) => s + (v - avg) ** 2, 0) / this.latencySamples.length
    );
    const score = Math.max(0, Math.min(100, 100 - avg * 0.5 - jitter * 2));
    useResilientWSStore.getState()._setQuality({
      latencyMs: Math.round(avg),
      jitterMs: Math.round(jitter),
      networkScore: Math.round(score),
    });
  }

  _calcFPS() {
    if (this.frameTimestamps.length < 2) return null;
    const span = this.frameTimestamps.at(-1) - this.frameTimestamps[0];
    return span > 0
      ? Math.round((this.frameTimestamps.length / (span / 1000)) * 10) / 10
      : null;
  }
}

export function createTelemetrySocket(path = "/ws/telemetry") {
  const getWsUrl = () => {
    const { wsUrl } = useAuthStore.getState();
    return wsUrl(path);
  };
  return new ResilientWebSocket(getWsUrl);
}

export function ConnectionStatusBar() {
  const { status, reconnectAttempt, nextReconnectIn, latencyMs,
          networkScore, frameRate, gaps, bufferedFrames } = useResilientWSStore();

  const colors = {
    connected: "#60d080",
    connecting: "#e0a040",
    reconnecting: "#e06040",
    disconnected: "#a04040",
  };
  const labels = {
    connected: "Live",
    connecting: "Connecting…",
    reconnecting: `Reconnecting in ${nextReconnectIn}s (attempt ${reconnectAttempt})`,
    disconnected: "Offline",
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, padding: "4px 12px",
      background: "#0d1525", borderRadius: 6, fontSize: 11, fontFamily: "monospace",
    }}>
      <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%",
          background: colors[status] ?? "#888",
          boxShadow: status === "connected" ? `0 0 6px ${colors.connected}` : "none",
        }} />
        <span style={{ color: colors[status] ?? "#888" }}>{labels[status]}</span>
      </span>

      {status === "connected" && latencyMs != null && (
        <>
          <span style={{ color: "#4060a0" }}>|</span>
          <span style={{ color: "#6080a0" }}>
            <span style={{ color: networkScore > 70 ? "#60d080" : networkScore > 40 ? "#e0a040" : "#e06040" }}>
              {latencyMs}ms
            </span>
            {" "}RTT
          </span>
          {frameRate != null && (
            <span style={{ color: "#6080a0" }}>{frameRate} fps</span>
          )}
        </>
      )}

      {bufferedFrames > 0 && (
        <span style={{ color: "#e0a040" }}>⟳ {bufferedFrames} buffered</span>
      )}

      {gaps.length > 0 && (
        <span style={{ color: "#e06040" }} title={`Last gap: ${(gaps[0].durationMs / 1000).toFixed(1)}s`}>
          ⚠ {gaps.length} gap{gaps.length > 1 ? "s" : ""} detected
        </span>
      )}
    </div>
  );
}