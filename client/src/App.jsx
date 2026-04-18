import { useCallback, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useTelemetryStore } from "./store/telemetryStore";
import { useAlertStore } from "./store/alertStore";
import { detectAlerts } from "./store/alertEngine";
import Scene from "./three/Scene";
import AlertFeed from "./components/AlertFeed";
import TelemetryGraphs from "./components/TelemetryGraphs";
import ControlPanel from "./components/ControlPanel";

const WS_URL = "ws://localhost:8000/ws/telemetry";

// Tab button for side panels
function TabBtn({ active, onClick, children, badge }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, background: active ? "#0d2030" : "transparent",
      border: "none", borderBottom: active ? "2px solid #00d4ff" : "2px solid transparent",
      color: active ? "#00d4ff" : "#445",
      fontFamily: "monospace", fontSize: 10, padding: "7px 4px",
      cursor: "pointer", position: "relative",
    }}>
      {children}
      {badge > 0 && (
        <span style={{
          position: "absolute", top: 3, right: 6,
          background: "#ff4444", color: "#fff",
          fontSize: 9, padding: "0 4px", borderRadius: 8,
        }}>{badge}</span>
      )}
    </button>
  );
}

export default function App() {
  const setSnapshot  = useTelemetryStore((s) => s.setSnapshot);
  const snapshot     = useTelemetryStore((s) => s.snapshot);
  const pushAlert    = useAlertStore((s) => s.push);
  const alerts       = useAlertStore((s) => s.alerts);
  const unackedCount = useAlertStore((s) => s.unackedCount);

  const [selectedId,  setSelectedId]  = useState(null);
  const [rightTab,    setRightTab]    = useState("control"); // control | telemetry | alerts
  const [leftTab,     setLeftTab]     = useState("3d");      // 3d | dish-list

  const handleMessage = useCallback((data) => {
    setSnapshot(data);
    const newAlerts = detectAlerts(data);
    newAlerts.forEach(pushAlert);
  }, [setSnapshot, pushAlert]);

  const { send } = useWebSocket(WS_URL, handleMessage);

  if (!snapshot) {
    return (
      <div style={{
        color: "#00ff88", background: "#020509", height: "100vh",
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", fontFamily: "monospace", gap: 12,
      }}>
        <div style={{ fontSize: 18, color: "#00d4ff" }}>ATMOS</div>
        <div style={{ fontSize: 12, color: "#334" }}>Connecting to backend...</div>
        <div style={{ width: 120, height: 2, background: "#0a1a2a", position: "relative", overflow: "hidden" }}>
          <div style={{
            position: "absolute", height: "100%", width: "40%",
            background: "#00d4ff",
            animation: "scan 1.5s infinite linear",
          }} />
        </div>
        <style>{`@keyframes scan { from { left: -40% } to { left: 100% } }`}</style>
      </div>
    );
  }

  const { alma, atmosphere, commanded_target, system, pointing_mode } = snapshot;
  const selected = alma.dishes.find((d) => d.id === selectedId);

  const critCount = alerts.filter((a) => a.severity === "critical" && !a.acked).length;
  const warnCount = alerts.filter((a) => a.severity === "warning"  && !a.acked).length;

  const windCrit = atmosphere.wind_ms >= 25;
  const windWarn = atmosphere.wind_ms >= 20;

  const pointingColor = {
    slewing: "#ffaa00", stow: "#ff8844", tracking: "#00ff88", idle: "#445",
  }[pointing_mode] || "#445";

  return (
    <div style={{
      background: "#020509", color: "#c0ccd8",
      height: "100vh", display: "flex", flexDirection: "column",
      fontFamily: "'Courier New', Courier, monospace", overflow: "hidden",
    }}>

      {/* ══ TOP BAR ══════════════════════════════════════════════════════════ */}
      <div style={{
        display: "flex", alignItems: "center", gap: 0,
        borderBottom: "1px solid #0d1e2e", background: "#040c14",
        flexShrink: 0, height: 38,
      }}>
        {/* Logo */}
        <div style={{ padding: "0 16px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center" }}>
          <span style={{ color: "#00d4ff", fontWeight: "bold", fontSize: 13, letterSpacing: "0.15em" }}>ATMOS</span>
        </div>

        {/* Pointing mode */}
        <div style={{ padding: "0 14px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#334", letterSpacing: "0.1em" }}>MODE</span>
          <span style={{ fontSize: 11, color: pointingColor, fontWeight: "bold" }}>
            {(pointing_mode || "TRACKING").toUpperCase()}
          </span>
        </div>

        {/* Target */}
        <div style={{ padding: "0 14px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#334" }}>TGT</span>
          <span style={{ fontSize: 11, color: "#aabbcc" }}>{commanded_target.name}</span>
          <span style={{ fontSize: 10, color: "#556" }}>
            Az {commanded_target.az_deg?.toFixed(1)}° El {commanded_target.el_deg?.toFixed(1)}°
          </span>
        </div>

        {/* Array status */}
        <div style={{ padding: "0 14px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#334" }}>ALMA</span>
          <span style={{ fontSize: 12, color: system?.fault_count > 0 ? "#ffaa00" : "#00ff88", fontWeight: "bold" }}>
            {alma.online_count}
          </span>
          <span style={{ fontSize: 10, color: "#334" }}>/ {alma.total_count}</span>
          <span style={{ fontSize: 10, color: "#556" }}>Tsys {alma.avg_tsys_k}K</span>
        </div>

        {/* Band */}
        <div style={{ padding: "0 14px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 9, color: "#334" }}>BAND</span>
          <span style={{ fontSize: 11, color: "#00ffcc" }}>B{system?.band} · {system?.freq_ghz} GHz</span>
        </div>

        {/* Atmosphere */}
        <div style={{ padding: "0 14px", borderRight: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#334" }}>ATM</span>
          <span style={{ fontSize: 10, color: "#aa77ff" }}>PWV {atmosphere.pwv_mm}mm</span>
          <span style={{ fontSize: 10, color: windCrit ? "#ff4444" : windWarn ? "#ffaa00" : "#778899" }}>
            {atmosphere.wind_ms}m/s
          </span>
          <span style={{ fontSize: 10, color: "#556" }}>{atmosphere.temp_c}°C</span>
        </div>

        {/* Alert badges */}
        <div style={{ padding: "0 10px", display: "flex", alignItems: "center", gap: 6 }}>
          {critCount > 0 && (
            <span onClick={() => setRightTab("alerts")} style={{
              background: "#ff3333", color: "#fff", fontSize: 9,
              padding: "2px 7px", borderRadius: 10, cursor: "pointer",
              animation: "alertpulse 1.2s ease-in-out infinite",
            }}>
              ⚠ {critCount} CRIT
            </span>
          )}
          {warnCount > 0 && (
            <span onClick={() => setRightTab("alerts")} style={{
              background: "#cc8800", color: "#fff", fontSize: 9,
              padding: "2px 7px", borderRadius: 10, cursor: "pointer",
            }}>
              ▲ {warnCount}
            </span>
          )}
        </div>

        {/* UTC clock */}
        <div style={{ marginLeft: "auto", padding: "0 14px", fontSize: 11, color: "#334", borderLeft: "1px solid #0d1e2e", height: "100%", display: "flex", alignItems: "center" }}>
          {new Date(snapshot.timestamp).toUTCString().slice(17, 25)} UTC
        </div>
      </div>

      {/* ══ MAIN AREA ════════════════════════════════════════════════════════ */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT — 3D viewport */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Scene selectedId={selectedId} onSelect={setSelectedId} />
        </div>

        {/* RIGHT — tabbed panel */}
        <div style={{ width: 230, borderLeft: "1px solid #0d1e2e", display: "flex", flexDirection: "column", overflow: "hidden", background: "#07101a" }}>

          {/* Tab bar */}
          <div style={{ display: "flex", borderBottom: "1px solid #0d1e2e", flexShrink: 0 }}>
            <TabBtn active={rightTab === "control"}   onClick={() => setRightTab("control")}>CONTROL</TabBtn>
            <TabBtn active={rightTab === "telemetry"} onClick={() => setRightTab("telemetry")}>TELEMETRY</TabBtn>
            <TabBtn active={rightTab === "alerts"}    onClick={() => setRightTab("alerts")} badge={unackedCount}>ALERTS</TabBtn>
          </div>

          <div style={{ flex: 1, overflow: "hidden" }}>
            {rightTab === "control"   && <ControlPanel send={send} snapshot={snapshot} selectedId={selectedId} />}
            {rightTab === "telemetry" && <TelemetryGraphs />}
            {rightTab === "alerts"    && <AlertFeed />}
          </div>
        </div>
      </div>

      {/* ══ BOTTOM — Dish status bar ════════════════════════════════════════ */}
      <div style={{
        height: 80, borderTop: "1px solid #0d1e2e", background: "#040c14",
        overflowX: "auto", overflowY: "hidden",
        display: "flex", alignItems: "center", gap: 3, padding: "0 10px",
        flexShrink: 0,
      }}>
        {alma.dishes.map((dish) => {
          const hasCrit = alerts.some((a) => a.dishId === dish.id && a.severity === "critical" && !a.acked);
          const isSelected = dish.id === selectedId;

          return (
            <div
              key={dish.id}
              onClick={() => setSelectedId(dish.id === selectedId ? null : dish.id)}
              title={`${dish.id} — ${dish.online ? `Tsys ${dish.tsys_k}K · Az ${dish.az_deg}°` : "OFFLINE"}`}
              style={{
                flexShrink: 0,
                width: 38, height: 58,
                background: isSelected ? "#0d2030" : hasCrit ? "#1a0808" : dish.online ? "#0a141e" : "#140808",
                border: `1px solid ${isSelected ? "#00d4ff" : hasCrit ? "#ff3333" : dish.online ? "#1a2a3a" : "#331111"}`,
                borderRadius: 3, cursor: "pointer",
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 2,
                padding: "4px 2px",
              }}
            >
              {/* Dish icon */}
              <div style={{
                width: 20, height: 12, borderRadius: "50% 50% 0 0",
                background: dish.online ? (hasCrit ? "#ff6644" : "#3a6688") : "#553333",
                transform: `rotate(${(dish.az_deg % 90) - 45}deg)`,
                transition: "transform 1s ease",
              }} />
              <div style={{ fontSize: 7, color: isSelected ? "#00d4ff" : dish.online ? "#778899" : "#664444", textAlign: "center", lineHeight: 1.2 }}>
                {dish.id.replace("DA-", "A").replace("DV-", "V")}
              </div>
              {dish.online ? (
                <div style={{ fontSize: 7, color: dish.tsys_k > 100 ? "#ffaa00" : "#336655" }}>
                  {dish.tsys_k?.toFixed(0)}K
                </div>
              ) : (
                <div style={{ fontSize: 7, color: "#553333" }}>OFF</div>
              )}
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes alertpulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}
