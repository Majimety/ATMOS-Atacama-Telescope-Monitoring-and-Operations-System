import { useCallback, useState, useEffect } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useTelemetryStore } from "./store/telemetryStore";
import { useAlertStore } from "./store/alertStore";
import { detectAlerts } from "./store/alertEngine";
import { useAuthStore, hasRole } from "./store/auth";
import Scene from "./three/Scene";
import AlertFeed from "./components/AlertFeed";
import TelemetryGraphs from "./components/TelemetryGraphs";
import ControlPanel from "./components/ControlPanel";
import SchedulerPanel from "./components/SchedulerPanel";
import LoginPage from "./pages/LoginPage";

// ── Helpers ───────────────────────────────────────────────────────────────────

function TabBtn({ active, onClick, children, badge }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        background: active ? "#0a1c2c" : "transparent",
        border: "none",
        borderBottom: `2px solid ${active ? "var(--accent-cyan)" : "transparent"}`,
        color: active ? "var(--accent-cyan)" : "var(--text-dim)",
        fontFamily: "var(--mono)",
        fontSize: 11,
        padding: "9px 4px",
        cursor: "pointer",
        position: "relative",
        transition: "color 0.15s, border-color 0.15s, background 0.15s",
        fontWeight: active ? "600" : "400",
        letterSpacing: "0.06em",
      }}
    >
      {children}
      {badge > 0 && (
        <span style={{
          position: "absolute",
          top: 5,
          right: 6,
          background: "var(--accent-red)",
          color: "#fff",
          fontSize: 9,
          fontWeight: "bold",
          padding: "1px 4px",
          borderRadius: 8,
          minWidth: 14,
          textAlign: "center",
          lineHeight: "14px",
        }}>
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

function Stat({ label, value, sub, color, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "0 14px",
        borderRight: "1px solid var(--border)",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 1,
        cursor: onClick ? "pointer" : "default",
        minWidth: 0,
        flexShrink: 1,
      }}
    >
      <div style={{ fontSize: 9, color: "var(--text-faint)", letterSpacing: "0.1em", fontWeight: "600", whiteSpace: "nowrap" }}>
        {label}
      </div>
      <div style={{ fontSize: 12, color: color || "var(--text-primary)", fontWeight: "600", whiteSpace: "nowrap", lineHeight: 1 }}>
        {value}
        {sub && <span style={{ fontSize: 10, color: "var(--text-dim)", fontWeight: "400", marginLeft: 4 }}>{sub}</span>}
      </div>
    </div>
  );
}

function DishCard({ dish, selected, hasCrit, onSelect, alerts }) {
  const bg = selected
    ? "#0d2030"
    : hasCrit ? "#1a0808"
    : dish.online ? "#070e16"
    : "#0d0808";

  const borderColor = selected
    ? "var(--accent-cyan)"
    : hasCrit ? "var(--accent-red)"
    : dish.online ? "#1a2a3a"
    : "#2a1111";

  const iconRotate = dish.online ? ((dish.az_deg || 0) % 180) - 90 : 0;

  return (
    <div
      onClick={() => onSelect(dish.id === selected ? null : dish.id)}
      title={`${dish.id} — ${dish.online ? `Tsys ${dish.tsys_k?.toFixed(0)}K · Az ${dish.az_deg?.toFixed(1)}° El ${dish.el_deg?.toFixed(1)}°` : "OFFLINE"}`}
      style={{
        flexShrink: 0,
        width: 44,
        height: 58,
        background: bg,
        border: `1px solid ${borderColor}`,
        borderRadius: 3,
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 2,
        padding: "4px 2px",
        transition: "transform 0.15s, box-shadow 0.15s",
        animation: "fadein 0.2s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-2px)";
        e.currentTarget.style.boxShadow = "0 3px 10px rgba(0,0,0,0.5)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <svg width="20" height="12" viewBox="0 0 20 12" style={{ transform: `rotate(${iconRotate}deg)`, transition: "transform 1s ease", flexShrink: 0 }}>
        <path
          d="M 0 12 A 10 12 0 0 1 20 12 Z"
          fill={dish.online ? (hasCrit ? "#ff6644" : "#3a6688") : "#4a2222"}
        />
        <line x1="10" y1="12" x2="10" y2="0" stroke={dish.online ? "#5a8899" : "#3a2222"} strokeWidth="1" />
      </svg>

      <div style={{
        fontSize: 8.5,
        color: selected ? "var(--accent-cyan)" : dish.online ? "#7a99aa" : "#5a3333",
        fontWeight: "600",
        letterSpacing: "0.02em",
        lineHeight: 1,
        textAlign: "center",
      }}>
        {dish.id.replace("DA-", "A").replace("DV-", "V")}
      </div>

      <div style={{
        fontSize: 8,
        color: !dish.online
          ? "#5a2222"
          : dish.tsys_k > 100 ? "var(--accent-yellow)"
          : "#2a5a44",
        fontWeight: "500",
        lineHeight: 1,
      }}>
        {dish.online ? `${dish.tsys_k?.toFixed(0)}K` : "OFF"}
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const setSnapshot  = useTelemetryStore((s) => s.setSnapshot);
  const snapshot     = useTelemetryStore((s) => s.snapshot);
  const pushAlert    = useAlertStore((s) => s.push);
  const alerts       = useAlertStore((s) => s.alerts);
  const unackedCount = useAlertStore((s) => s.unackedCount);

  const [selectedId, setSelectedId] = useState(null);
  const [rightTab,   setRightTab]   = useState("control");

  const authUser    = useAuthStore((s) => s.user);
  const authLogout  = useAuthStore((s) => s.logout);
  const demoMode    = useAuthStore((s) => s.demoMode);
  const isAuth      = useAuthStore((s) => s.isAuthenticated);
  const getWsUrl    = useAuthStore((s) => s.wsUrl);
  const [showLogin, setShowLogin] = useState(!isAuth());

  const wsUrl = getWsUrl("/ws/telemetry");

  const handleMessage = useCallback((data) => {
    setSnapshot(data);
    detectAlerts(data).forEach(pushAlert);
  }, [setSnapshot, pushAlert]);

  const { send } = useWebSocket(wsUrl, handleMessage);

  if (!snapshot) {
    return (
      <div style={{
        color: "var(--accent-green)",
        background: "var(--bg-deep)",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--mono)",
        gap: 20,
      }}>
        <div style={{ fontSize: 28, color: "var(--accent-cyan)", fontWeight: "bold", letterSpacing: "0.3em" }}>
          ATMOS
        </div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", letterSpacing: "0.15em" }}>
          CONNECTING TO BACKEND
        </div>
        <div style={{ width: 200, height: 2, background: "#0a1a2a", position: "relative", overflow: "hidden", borderRadius: 1 }}>
          <div style={{
            position: "absolute",
            height: "100%",
            width: "40%",
            background: "linear-gradient(90deg, transparent, var(--accent-cyan), transparent)",
            animation: "scan 1.5s infinite ease-in-out",
          }} />
        </div>
      </div>
    );
  }

  if (showLogin) {
    return <LoginPage onLogin={() => setShowLogin(false)} />;
  }

  const { alma, atmosphere, commanded_target, system, pointing_mode } = snapshot;

  const critCount = alerts.filter((a) => a.severity === "critical" && !a.acked).length;
  const warnCount = alerts.filter((a) => a.severity === "warning"  && !a.acked).length;

  const windCrit = atmosphere.wind_ms >= 25;
  const windWarn = atmosphere.wind_ms >= 20;

  const pointingColor = {
    slewing:  "var(--accent-yellow)",
    stow:     "#ff8844",
    tracking: "var(--accent-green)",
    idle:     "var(--text-dim)",
  }[pointing_mode] || "var(--text-dim)";

  const utcTime = new Date(snapshot.timestamp).toUTCString().slice(17, 25);

  return (
    <div style={{
      background: "var(--bg-deep)",
      color: "var(--text-primary)",
      height: "100vh",
      width: "100vw",
      display: "flex",
      flexDirection: "column",
      fontFamily: "var(--mono)",
      overflow: "hidden",
    }}>

      <div style={{
        display: "flex",
        alignItems: "stretch",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-panel)",
        flexShrink: 0,
        height: 44,
        overflow: "hidden",
      }}>
        <div style={{
          padding: "0 18px",
          borderRight: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          flexShrink: 0,
        }}>
          <span style={{ color: "var(--accent-cyan)", fontWeight: "bold", fontSize: 13, letterSpacing: "0.25em" }}>
            ATMOS
          </span>
        </div>

        <Stat label="MODE" value={(pointing_mode || "TRACKING").toUpperCase()} color={pointingColor} />
        <Stat label="TARGET" value={commanded_target.name} sub={`Az ${commanded_target.az_deg?.toFixed(1)}° El ${commanded_target.el_deg?.toFixed(1)}°`} color="var(--text-primary)" />
        <Stat label="ARRAY" value={`${alma.online_count} / ${alma.total_count}`} sub={`Tsys ${alma.avg_tsys_k}K`} color={system?.fault_count > 0 ? "var(--accent-yellow)" : "var(--accent-green)"} />
        <Stat label="BAND" value={`B${system?.band}`} sub={`${system?.freq_ghz} GHz`} color="var(--accent-teal)" />
        <Stat label="PWV" value={`${atmosphere.pwv_mm} mm`} color="var(--accent-purple)" />
        <Stat label="WIND" value={`${atmosphere.wind_ms} m/s`} color={windCrit ? "var(--accent-red)" : windWarn ? "var(--accent-yellow)" : "var(--text-dim)"} />
        <Stat label="TEMP" value={`${atmosphere.temp_c}°C`} />

        {(critCount > 0 || warnCount > 0) && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", flexShrink: 0 }}>
            {critCount > 0 && (
              <button onClick={() => setRightTab("alerts")} style={{ background: "var(--accent-red)", color: "#fff", fontSize: 10, fontWeight: "bold", padding: "4px 10px", borderRadius: 10, cursor: "pointer", border: "none", fontFamily: "var(--mono)", animation: "alertpulse 1.4s ease-in-out infinite", whiteSpace: "nowrap" }}>
                ⚠ {critCount} CRIT
              </button>
            )}
            {warnCount > 0 && (
              <button onClick={() => setRightTab("alerts")} style={{ background: "#7a5500", color: "var(--accent-yellow)", fontSize: 10, fontWeight: "bold", padding: "4px 10px", borderRadius: 10, cursor: "pointer", border: "1px solid #aa7700", fontFamily: "var(--mono)", whiteSpace: "nowrap" }}>
                ▲ {warnCount}
              </button>
            )}
          </div>
        )}

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "stretch", flexShrink: 0 }}>
          {authUser && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", borderLeft: "1px solid var(--border)", fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.06em" }}>
              <span style={{ color: { viewer:"#00d4ff", operator:"#00ff88", engineer:"#ffaa00", admin:"#ff6644" }[authUser.role] ?? "#00d4ff", fontWeight: 700 }}>
                {authUser.role.toUpperCase()}
              </span>
              <span style={{ color: "var(--text-faint)" }}>{authUser.username}</span>
              {demoMode && <span style={{ color: "#333", fontSize: 9 }}>DEMO</span>}
              <button onClick={() => { authLogout(); setShowLogin(true); }} style={{ background: "transparent", border: "1px solid #1a2a3a", color: "#334455", fontFamily: "monospace", fontSize: 9, padding: "2px 6px", cursor: "pointer", letterSpacing: "0.05em" }}>
                LOGOUT
              </button>
            </div>
          )}
          <div style={{ padding: "0 16px", borderLeft: "1px solid var(--border)", display: "flex", alignItems: "center", fontSize: 11, color: "var(--text-faint)", fontWeight: "500", letterSpacing: "0.05em" }}>
            {utcTime} UTC
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}>

        <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
          <Scene selectedId={selectedId} onSelect={setSelectedId} />

          {selectedId && (() => {
            const dish = alma.dishes.find((d) => d.id === selectedId);
            if (!dish) return null;
            return (
              <div style={{
                position: "absolute", top: 12, left: 12,
                background: "rgba(4,12,20,0.92)",
                border: "1px solid var(--border-mid)",
                borderLeft: "3px solid var(--accent-teal)",
                borderRadius: 4, padding: "10px 14px",
                fontFamily: "var(--mono)", fontSize: 11, minWidth: 180,
                animation: "fadein 0.2s ease",
              }}>
                <div style={{ color: "var(--accent-teal)", fontWeight: "bold", marginBottom: 6, fontSize: 12 }}>
                  {dish.id}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3px 14px", color: "var(--text-dim)" }}>
                  <span>Az</span><span style={{ color: "var(--text-primary)" }}>{dish.az_deg?.toFixed(2)}°</span>
                  <span>El</span><span style={{ color: "var(--text-primary)" }}>{dish.el_deg?.toFixed(2)}°</span>
                  <span>Tsys</span>
                  <span style={{ color: dish.tsys_k > 100 ? "var(--accent-yellow)" : "var(--accent-green)" }}>
                    {dish.tsys_k?.toFixed(1)} K
                  </span>
                  <span>Signal</span><span style={{ color: "var(--text-primary)" }}>{dish.signal_dbm?.toFixed(1)} dBm</span>
                  <span>Status</span>
                  <span style={{ color: dish.online ? "var(--accent-green)" : "var(--accent-red)" }}>
                    {dish.online ? "ONLINE" : "OFFLINE"}
                  </span>
                </div>
                {!dish.online && (
                  <button
                    onClick={() => send({ type: "clear_fault", dishId: dish.id })}
                    style={{
                      marginTop: 8, width: "100%",
                      background: "transparent", border: "1px solid var(--accent-green)",
                      color: "var(--accent-green)", fontFamily: "var(--mono)",
                      fontSize: 10, padding: "4px 8px", cursor: "pointer", borderRadius: 3,
                    }}
                  >
                    CLEAR FAULT
                  </button>
                )}
              </div>
            );
          })()}
        </div>

        <div style={{ width: 300, borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg-card)", flexShrink: 0 }}>
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", flexShrink: 0, background: "var(--bg-panel)" }}>
            <TabBtn active={rightTab === "control"}   onClick={() => setRightTab("control")}>CONTROL</TabBtn>
            <TabBtn active={rightTab === "telemetry"} onClick={() => setRightTab("telemetry")}>TELEMETRY</TabBtn>
            <TabBtn active={rightTab === "scheduler"} onClick={() => setRightTab("scheduler")}>SCHED</TabBtn>
            <TabBtn active={rightTab === "alerts"}    onClick={() => setRightTab("alerts")} badge={unackedCount}>ALERTS</TabBtn>
          </div>

          <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
            {rightTab === "control"   && <ControlPanel send={send} snapshot={snapshot} selectedId={selectedId} />}
            {rightTab === "telemetry" && <TelemetryGraphs />}
            {rightTab === "scheduler" && <SchedulerPanel />}
            {rightTab === "alerts"    && <AlertFeed />}
          </div>
        </div>
      </div>

      <div style={{ height: 70, borderTop: "1px solid var(--border)", background: "var(--bg-panel)", display: "flex", alignItems: "center", gap: 3, padding: "0 10px", flexShrink: 0, overflowX: "auto", overflowY: "hidden" }}>
        <div style={{ flexShrink: 0, width: 36, height: 58, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, marginRight: 4 }}>
          <div style={{ fontSize: 8, color: "var(--text-faint)", letterSpacing: "0.1em", writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
            ALMA
          </div>
          <div style={{ width: 1, flex: 1, background: "var(--border)" }} />
        </div>

        {alma.dishes.map((dish) => {
          const hasCrit = alerts.some((a) => a.dishId === dish.id && a.severity === "critical" && !a.acked);
          return (
            <DishCard key={dish.id} dish={dish} selected={selectedId} hasCrit={hasCrit} onSelect={setSelectedId} alerts={alerts} />
          );
        })}
      </div>
    </div>
  );
}