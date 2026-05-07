import { useAlertStore } from "../store/alertStore";

const SEV = {
  critical: { color: "#ff4444", bg: "#120303", border: "#ff4444", icon: "⚠", label: "CRIT" },
  warning:  { color: "#ffaa00", bg: "#120d00", border: "#ffaa00", icon: "▲", label: "WARN" },
  info:     { color: "#00d4ff", bg: "#000d12", border: "#00d4ff", icon: "●", label: "INFO" },
};

function ts(date) {
  return date.toTimeString().slice(0, 8);
}

export default function AlertFeed() {
  const alerts   = useAlertStore((s) => s.alerts);
  const ackAll   = useAlertStore((s) => s.ackAll);
  const clear    = useAlertStore((s) => s.clear);

  const critCount = alerts.filter((a) => a.severity === "critical" && !a.acked).length;
  const warnCount = alerts.filter((a) => a.severity === "warning"  && !a.acked).length;
  const unacked   = alerts.filter((a) => !a.acked).length;

  return (
    <div style={S.wrap}>

      {/* ── Header bar ── */}
      <div style={S.header}>
        <span style={S.title}>EVENT LOG</span>

        {/* Badge counts — แสดงเฉพาะถ้ามี */}
        {critCount > 0 && (
          <span style={{ ...S.badge, background: "#ff4444", color: "#fff" }}>
            {critCount} CRIT
          </span>
        )}
        {warnCount > 0 && (
          <span style={{ ...S.badge, background: "#cc8800", color: "#fff" }}>
            {warnCount} WARN
          </span>
        )}

        {/* Event count */}
        <span style={S.count}>{alerts.length} events</span>

        {/* Action buttons */}
        <button
          onClick={ackAll}
          disabled={unacked === 0}
          style={{ ...S.actionBtn, color: unacked > 0 ? "#336644" : "#1a2a1a", borderColor: unacked > 0 ? "#1a4a2a" : "#0d1a0d" }}
        >
          ACK ALL
        </button>
        <button
          onClick={clear}
          disabled={alerts.length === 0}
          style={{ ...S.actionBtn, color: alerts.length > 0 ? "#664433" : "#1a1010", borderColor: alerts.length > 0 ? "#4a1a1a" : "#1a0d0d" }}
        >
          CLEAR
        </button>
      </div>

      {/* ── Severity summary strip — แสดงเมื่อมี alert ── */}
      {alerts.length > 0 && (
        <div style={S.summaryBar}>
          <div style={S.summaryItem}>
            <span style={{ color: "#ff4444" }}>⚠</span>
            <span style={{ color: "#cc3333" }}>{alerts.filter(a => a.severity === "critical").length}</span>
            <span style={{ color: "#1e3344" }}>CRIT</span>
          </div>
          <div style={S.summaryDivider} />
          <div style={S.summaryItem}>
            <span style={{ color: "#cc8800" }}>▲</span>
            <span style={{ color: "#aa7700" }}>{alerts.filter(a => a.severity === "warning").length}</span>
            <span style={{ color: "#1e3344" }}>WARN</span>
          </div>
          <div style={S.summaryDivider} />
          <div style={S.summaryItem}>
            <span style={{ color: "#0088aa" }}>●</span>
            <span style={{ color: "#007799" }}>{alerts.filter(a => a.severity === "info").length}</span>
            <span style={{ color: "#1e3344" }}>INFO</span>
          </div>
          <div style={{ marginLeft: "auto", fontSize: 9, color: "#1e3344" }}>
            {unacked > 0 ? `${unacked} unacked` : "all acked"}
          </div>
        </div>
      )}

      {/* ── Alert list ── */}
      <div style={S.list}>
        {alerts.length === 0 && (
          <div style={S.emptyState}>
            <div style={{ fontSize: 20, marginBottom: 8, color: "#0d2030" }}>◉</div>
            <div style={{ fontSize: 11, color: "#1a3344", letterSpacing: "0.08em" }}>NO EVENTS</div>
            <div style={{ fontSize: 9, color: "#0d1e2a", marginTop: 4 }}>System nominal</div>
          </div>
        )}

        {alerts.map((alert) => {
          const s = SEV[alert.severity] ?? SEV.info;
          return (
            <div key={alert.id} style={{
              padding:      "6px 10px 6px 0",
              borderBottom: "1px solid #080f16",
              borderLeft:   `3px solid ${alert.acked ? "#0d1820" : s.border}`,
              background:   alert.acked ? "transparent" : s.bg,
              opacity:      alert.acked ? 0.4 : 1,
              display:      "flex",
              gap:          0,
            }}>
              {/* Severity icon column */}
              <div style={{
                width:      32,
                flexShrink: 0,
                display:    "flex",
                alignItems: "flex-start",
                justifyContent: "center",
                paddingTop: 1,
                fontSize:   11,
                color:      alert.acked ? "#1a2a3a" : s.color,
              }}>
                {s.icon}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 2 }}>
                  <span style={{
                    fontSize:   10,
                    fontWeight: 700,
                    color:      alert.acked ? "#1e3344" : s.color,
                    overflow:   "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex:       1,
                    marginRight: 6,
                  }}>
                    {alert.title}
                  </span>
                  <span style={{ fontSize: 9, color: "#1a3344", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
                    {ts(alert.timestamp)}
                  </span>
                </div>
                <div style={{
                  fontSize:   9,
                  color:      "#335566",
                  lineHeight: 1.5,
                  overflow:   "hidden",
                  display:    "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                }}>
                  {alert.message}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  wrap: {
    display:       "flex",
    flexDirection: "column",
    height:        "100%",
    background:    "#060e18",
    fontFamily:    "monospace",
    overflow:      "hidden",
  },

  // ── Header: single row, ไม่ wrap ─────────────────────────────────────────
  header: {
    display:      "flex",
    alignItems:   "center",
    gap:          6,
    padding:      "0 10px",
    height:       32,
    borderBottom: "1px solid #0c1820",
    background:   "#040c12",
    flexShrink:   0,
    flexWrap:     "nowrap",
    overflow:     "hidden",
  },
  title: {
    color:        "#00c4ee",
    fontSize:     11,
    fontWeight:   700,
    letterSpacing:"0.08em",
    whiteSpace:   "nowrap",
    flexShrink:   0,
  },
  badge: {
    fontSize:     9,
    fontWeight:   700,
    padding:      "1px 6px",
    borderRadius: 10,
    whiteSpace:   "nowrap",
    flexShrink:   0,
  },
  count: {
    marginLeft:   "auto",
    color:        "#1a3344",
    fontSize:     9,
    whiteSpace:   "nowrap",
    flexShrink:   0,
  },
  actionBtn: {
    background:   "transparent",
    border:       "1px solid",
    fontFamily:   "monospace",
    fontSize:     9,
    padding:      "2px 7px",
    cursor:       "pointer",
    whiteSpace:   "nowrap",
    flexShrink:   0,
    letterSpacing:"0.04em",
  },

  // ── Summary strip ─────────────────────────────────────────────────────────
  summaryBar: {
    display:      "flex",
    alignItems:   "center",
    gap:          8,
    padding:      "4px 10px",
    borderBottom: "1px solid #0c1820",
    background:   "#050b14",
    flexShrink:   0,
  },
  summaryItem: {
    display: "flex",
    gap:     4,
    alignItems: "center",
    fontSize: 9,
  },
  summaryDivider: {
    width:      1,
    height:     10,
    background: "#0d1e2a",
  },

  // ── Alert list ────────────────────────────────────────────────────────────
  list: {
    flex:           1,
    overflowY:      "auto",
    overflowX:      "hidden",
    minHeight:      0,
    scrollbarWidth: "thin",
    scrollbarColor: "#0c2030 #040c12",
  },
  emptyState: {
    padding:   "32px 12px",
    textAlign: "center",
  },
};