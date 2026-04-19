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

// Improved Tab button
function TabBtn({ active, onClick, children, badge }) {
  return (
    <button onClick={onClick} style={{
      flex: 1,
      background: active ? "#0d2030" : "transparent",
      border: "none",
      borderBottom: active ? "2px solid #00d4ff" : "2px solid transparent",
      color: active ? "#00d4ff" : "#6688aa",
      fontFamily: "monospace",
      fontSize: 11,
      padding: "10px 6px",
      cursor: "pointer",
      position: "relative",
      transition: "all 0.2s ease",
      fontWeight: active ? "600" : "400",
    }}>
      {children}
      {badge > 0 && (
        <span style={{
          position: "absolute",
          top: 4,
          right: 8,
          background: "#ff4444",
          color: "#fff",
          fontSize: 10,
          fontWeight: "bold",
          padding: "1px 5px",
          borderRadius: 10,
          minWidth: 16,
          textAlign: "center",
        }}>
          {badge}
        </span>
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
  const [rightTab,    setRightTab]    = useState("control");
  const [leftTab,     setLeftTab]     = useState("3d");

  const handleMessage = useCallback((data) => {
    setSnapshot(data);
    const newAlerts = detectAlerts(data);
    newAlerts.forEach(pushAlert);
  }, [setSnapshot, pushAlert]);

  const { send } = useWebSocket(WS_URL, handleMessage);

  if (!snapshot) {
    return (
      <div style={{
        color: "#00ff88",
        background: "#020509",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "monospace",
        gap: 16,
      }}>
        <div style={{ fontSize: 24, color: "#00d4ff", fontWeight: "bold", letterSpacing: "0.2em" }}>
          ATMOS
        </div>
        <div style={{ fontSize: 13, color: "#556677" }}>
          Connecting to backend...
        </div>
        <div style={{
          width: 200,
          height: 3,
          background: "#0a1a2a",
          position: "relative",
          overflow: "hidden",
          borderRadius: 2,
        }}>
          <div style={{
            position: "absolute",
            height: "100%",
            width: "40%",
            background: "linear-gradient(90deg, transparent, #00d4ff, transparent)",
            animation: "scan 1.5s infinite ease-in-out",
          }} />
        </div>
        <style>{`
          @keyframes scan {
            from { left: -40% }
            to { left: 100% }
          }
        `}</style>
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
    slewing: "#ffaa00",
    stow: "#ff8844",
    tracking: "#00ff88",
    idle: "#6688aa",
  }[pointing_mode] || "#6688aa";

  return (
    <div style={{
      background: "#020509",
      color: "#c0ccd8",
      height: "100vh",
      display: "flex",
      flexDirection: "column",
      fontFamily: "'Courier New', Courier, monospace",
      overflow: "hidden",
    }}>

      {/* ══ TOP BAR ══════════════════════════════════════════════════════════ */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        borderBottom: "1px solid #0d1e2e",
        background: "#040c14",
        flexShrink: 0,
        height: 44,
      }}>
        {/* Logo */}
        <div style={{
          padding: "0 20px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
        }}>
          <span style={{
            color: "#00d4ff",
            fontWeight: "bold",
            fontSize: 14,
            letterSpacing: "0.2em",
          }}>
            ATMOS
          </span>
        </div>

        {/* Pointing mode */}
        <div style={{
          padding: "0 16px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <span style={{
            fontSize: 10,
            color: "#445566",
            letterSpacing: "0.1em",
            fontWeight: "600",
          }}>
            MODE
          </span>
          <span style={{
            fontSize: 12,
            color: pointingColor,
            fontWeight: "bold",
          }}>
            {(pointing_mode || "TRACKING").toUpperCase()}
          </span>
        </div>

        {/* Target */}
        <div style={{
          padding: "0 16px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
          minWidth: 280,
        }}>
          <span style={{ fontSize: 10, color: "#445566", fontWeight: "600" }}>
            TARGET
          </span>
          <span style={{ fontSize: 12, color: "#aabbcc", fontWeight: "500" }}>
            {commanded_target.name}
          </span>
          <span style={{ fontSize: 11, color: "#6688aa" }}>
            Az {commanded_target.az_deg?.toFixed(1)}° El {commanded_target.el_deg?.toFixed(1)}°
          </span>
        </div>

        {/* Array status */}
        <div style={{
          padding: "0 16px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <span style={{ fontSize: 10, color: "#445566", fontWeight: "600" }}>
            ARRAY
          </span>
          <span style={{
            fontSize: 13,
            color: system?.fault_count > 0 ? "#ffaa00" : "#00ff88",
            fontWeight: "bold",
          }}>
            {alma.online_count}
          </span>
          <span style={{ fontSize: 11, color: "#445566" }}>
            / {alma.total_count}
          </span>
          <span style={{ fontSize: 11, color: "#6688aa" }}>
            Tsys {alma.avg_tsys_k}K
          </span>
        </div>

        {/* Band */}
        <div style={{
          padding: "0 16px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          <span style={{ fontSize: 10, color: "#445566", fontWeight: "600" }}>
            BAND
          </span>
          <span style={{ fontSize: 12, color: "#00ffcc", fontWeight: "500" }}>
            B{system?.band} · {system?.freq_ghz} GHz
          </span>
        </div>

        {/* Atmosphere */}
        <div style={{
          padding: "0 16px",
          borderRight: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <span style={{ fontSize: 10, color: "#445566", fontWeight: "600" }}>
            ATM
          </span>
          <span style={{ fontSize: 11, color: "#aa77ff" }}>
            PWV {atmosphere.pwv_mm}mm
          </span>
          <span style={{
            fontSize: 11,
            color: windCrit ? "#ff4444" : windWarn ? "#ffaa00" : "#6688aa",
            fontWeight: windCrit || windWarn ? "bold" : "normal",
          }}>
            {atmosphere.wind_ms}m/s
          </span>
          <span style={{ fontSize: 11, color: "#6688aa" }}>
            {atmosphere.temp_c}°C
          </span>
        </div>

        {/* Alert badges */}
        <div style={{
          padding: "0 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          {critCount > 0 && (
            <span onClick={() => setRightTab("alerts")} style={{
              background: "#ff3333",
              color: "#fff",
              fontSize: 10,
              fontWeight: "bold",
              padding: "4px 10px",
              borderRadius: 12,
              cursor: "pointer",
              animation: "alertpulse 1.2s ease-in-out infinite",
            }}>
              ⚠ {critCount} CRIT
            </span>
          )}
          {warnCount > 0 && (
            <span onClick={() => setRightTab("alerts")} style={{
              background: "#cc8800",
              color: "#fff",
              fontSize: 10,
              fontWeight: "bold",
              padding: "4px 10px",
              borderRadius: 12,
              cursor: "pointer",
            }}>
              ▲ {warnCount}
            </span>
          )}
        </div>

        {/* UTC clock */}
        <div style={{
          marginLeft: "auto",
          padding: "0 20px",
          fontSize: 12,
          color: "#445566",
          borderLeft: "1px solid #0d1e2e",
          height: "100%",
          display: "flex",
          alignItems: "center",
          fontWeight: "500",
        }}>
          {new Date(snapshot.timestamp).toUTCString().slice(17, 25)} UTC
        </div>
      </div>

      {/* ══ MAIN AREA ════════════════════════════════════════════════════════ */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT — 3D viewport */}
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}>
          <Scene selectedId={selectedId} onSelect={setSelectedId} />
        </div>

        {/* RIGHT — tabbed panel (increased width) */}
        <div style={{
          width: 320,
          borderLeft: "1px solid #0d1e2e",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          background: "#07101a",
        }}>

          {/* Tab bar */}
          <div style={{
            display: "flex",
            borderBottom: "1px solid #0d1e2e",
            flexShrink: 0,
          }}>
            <TabBtn
              active={rightTab === "control"}
              onClick={() => setRightTab("control")}
            >
              CONTROL
            </TabBtn>
            <TabBtn
              active={rightTab === "telemetry"}
              onClick={() => setRightTab("telemetry")}
            >
              TELEMETRY
            </TabBtn>
            <TabBtn
              active={rightTab === "alerts"}
              onClick={() => setRightTab("alerts")}
              badge={unackedCount}
            >
              ALERTS
            </TabBtn>
          </div>

          <div style={{ flex: 1, overflow: "hidden" }}>
            {rightTab === "control"   && <ControlPanel send={send} snapshot={snapshot} selectedId={selectedId} />}
            {rightTab === "telemetry" && <TelemetryGraphs />}
            {rightTab === "alerts"    && <AlertFeed />}
          </div>
        </div>
      </div>

      {/* ══ BOTTOM — Dish status bar (improved) ════════════════════════════════ */}
      <div style={{
        height: 72,
        borderTop: "1px solid #0d1e2e",
        background: "#040c14",
        overflowX: "auto",
        overflowY: "hidden",
        display: "flex",
        alignItems: "center",
        gap: 4,
        padding: "0 12px",
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
                width: 42,
                height: 56,
                background: isSelected
                  ? "#0d2030"
                  : hasCrit
                  ? "#1a0808"
                  : dish.online
                  ? "#0a141e"
                  : "#0f0808",
                border: `1px solid ${
                  isSelected
                    ? "#00d4ff"
                    : hasCrit
                    ? "#ff3333"
                    : dish.online
                    ? "#1a2a3a"
                    : "#331111"
                }`,
                borderRadius: 4,
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 3,
                padding: "5px 3px",
                transition: "all 0.2s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-2px)";
                e.currentTarget.style.boxShadow = "0 4px 8px rgba(0,0,0,0.3)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              {/* Dish icon */}
              <div style={{
                width: 22,
                height: 14,
                borderRadius: "50% 50% 0 0",
                background: dish.online
                  ? hasCrit
                    ? "#ff6644"
                    : "#3a6688"
                  : "#553333",
                transform: `rotate(${(dish.az_deg % 90) - 45}deg)`,
                transition: "transform 1s ease",
              }} />
              
              {/* Dish ID */}
              <div style={{
                fontSize: 9,
                color: isSelected
                  ? "#00d4ff"
                  : dish.online
                  ? "#8899aa"
                  : "#664444",
                textAlign: "center",
                lineHeight: 1.2,
                fontWeight: "500",
              }}>
                {dish.id.replace("DA-", "A").replace("DV-", "V")}
              </div>
              
              {/* Tsys or Status */}
              {dish.online ? (
                <div style={{
                  fontSize: 9,
                  color: dish.tsys_k > 100 ? "#ffaa00" : "#336655",
                  fontWeight: "500",
                }}>
                  {dish.tsys_k?.toFixed(0)}K
                </div>
              ) : (
                <div style={{
                  fontSize: 8,
                  color: "#664444",
                  fontWeight: "500",
                }}>
                  OFF
                </div>
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