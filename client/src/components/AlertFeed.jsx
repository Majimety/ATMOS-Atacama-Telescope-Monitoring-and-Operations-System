import { useAlertStore } from "../store/alertStore";

const SEV = {
  critical: { color: "#ff4444", bg: "#1a0505", border: "#ff4444", icon: "⚠", label: "CRIT" },
  warning:  { color: "#ffaa00", bg: "#1a1000", border: "#ffaa00", icon: "▲", label: "WARN" },
  info:     { color: "#00d4ff", bg: "#001018", border: "#00d4ff", icon: "●", label: "INFO" },
};

function ts(date) {
  return date.toTimeString().slice(0, 8);
}

export default function AlertFeed() {
  const alerts = useAlertStore((s) => s.alerts);
  const ackAll = useAlertStore((s) => s.ackAll);
  const clear  = useAlertStore((s) => s.clear);

  const critCount = alerts.filter((a) => a.severity === "critical" && !a.acked).length;
  const warnCount = alerts.filter((a) => a.severity === "warning"  && !a.acked).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#07101a", fontFamily: "monospace" }}>
      {/* Header */}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid #1a2a3a", display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <span style={{ color: "#00d4ff", fontSize: 12, fontWeight: "bold" }}>EVENT LOG</span>

        {critCount > 0 && (
          <span style={{ background: "#ff4444", color: "#fff", fontSize: 10, padding: "1px 7px", borderRadius: 10 }}>
            {critCount} CRIT
          </span>
        )}
        {warnCount > 0 && (
          <span style={{ background: "#ffaa00", color: "#000", fontSize: 10, padding: "1px 7px", borderRadius: 10 }}>
            {warnCount} WARN
          </span>
        )}
        <span style={{ marginLeft: "auto", color: "#334", fontSize: 10 }}>{alerts.length} events</span>

        <button onClick={ackAll} style={{ background: "transparent", border: "1px solid #1a3a2a", color: "#336644", fontSize: 10, padding: "2px 8px", cursor: "pointer", fontFamily: "monospace" }}>
          ACK ALL
        </button>
        <button onClick={clear} style={{ background: "transparent", border: "1px solid #2a1a1a", color: "#664433", fontSize: 10, padding: "2px 8px", cursor: "pointer", fontFamily: "monospace" }}>
          CLEAR
        </button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {alerts.length === 0 && (
          <div style={{ padding: 24, color: "#334", fontSize: 12, textAlign: "center" }}>
            No events — system nominal
          </div>
        )}
        {alerts.map((alert) => {
          const s = SEV[alert.severity] || SEV.info;
          return (
            <div key={alert.id} style={{
              padding: "7px 12px",
              borderBottom: "1px solid #0a141e",
              borderLeft: `3px solid ${alert.acked ? "#222" : s.border}`,
              background: alert.acked ? "transparent" : s.bg,
              opacity: alert.acked ? 0.45 : 1,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ color: alert.acked ? "#446" : s.color, fontSize: 11, fontWeight: "bold" }}>
                  {s.icon} {alert.title}
                </span>
                <span style={{ color: "#334", fontSize: 10 }}>{ts(alert.timestamp)}</span>
              </div>
              <div style={{ color: "#667", fontSize: 10, lineHeight: 1.5 }}>{alert.message}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
