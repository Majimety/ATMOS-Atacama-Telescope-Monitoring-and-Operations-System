import { useTelemetryStore } from "../store/telemetryStore";

// Mini SVG sparkline — ไม่ใช้ library เพื่อ performance
function Sparkline({ data, color, min, max, height = 36, width = 160 }) {
  if (data.length < 2) return <div style={{ width, height, background: "#0a141e" }} />;

  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * w;
    const y = pad + h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const lastVal = data[data.length - 1];
  const lastX = pad + w;
  const lastY = pad + h - ((lastVal - min) / range) * h;

  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.2" opacity="0.8" />
      <circle cx={lastX} cy={lastY} r="2.5" fill={color} />
    </svg>
  );
}

function MetricRow({ label, value, unit, data, color, min, max, warn, crit }) {
  const isWarn = warn !== undefined && value >= warn;
  const isCrit = crit !== undefined && value >= crit;
  const valColor = isCrit ? "#ff4444" : isWarn ? "#ffaa00" : "#e0e0e0";

  return (
    <div style={{ padding: "8px 12px", borderBottom: "1px solid #0d1a24" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, alignItems: "baseline" }}>
        <span style={{ fontSize: 10, color: "#556", letterSpacing: "0.08em" }}>{label}</span>
        <span style={{ fontSize: 14, color: valColor, fontWeight: "bold" }}>
          {typeof value === "number" ? value.toFixed(2) : "—"}
          <span style={{ fontSize: 10, color: "#445", marginLeft: 3 }}>{unit}</span>
        </span>
      </div>
      <Sparkline data={data} color={color} min={min} max={max} width={186} height={32} />
    </div>
  );
}

export default function TelemetryGraphs() {
  const history  = useTelemetryStore((s) => s.history);
  const snapshot = useTelemetryStore((s) => s.snapshot);

  if (!snapshot || history.length === 0) return (
    <div style={{ padding: 16, color: "#334", fontSize: 12, fontFamily: "monospace" }}>
      Acquiring data...
    </div>
  );

  const atm = snapshot.atmosphere;
  const sys = snapshot.system;

  // tau_225ghz จริงอยู่ที่ ~0.030–0.060 scale เป็น mτ (×1000) เพื่ออ่านง่าย
  const tauScaled = atm.tau_225ghz * 1000;

  return (
    <div style={{ fontFamily: "monospace", background: "#07101a", height: "100%", overflowY: "auto" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid #1a2a3a", fontSize: 12, color: "#00d4ff" }}>
        TELEMETRY — LIVE
      </div>

      {/* System info */}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid #0d1a24", display: "flex", gap: 16 }}>
        <div style={{ fontSize: 10 }}>
          <div style={{ color: "#556" }}>BAND</div>
          <div style={{ color: "#00ffcc", fontSize: 13 }}>B{sys?.band} · {sys?.freq_ghz} GHz</div>
        </div>
        <div style={{ fontSize: 10 }}>
          <div style={{ color: "#556" }}>MODE</div>
          <div style={{ color: "#aabbcc", fontSize: 11, textTransform: "uppercase" }}>{sys?.obs_mode}</div>
        </div>
        <div style={{ fontSize: 10 }}>
          <div style={{ color: "#556" }}>FAULTS</div>
          <div style={{ color: sys?.fault_count > 0 ? "#ff4444" : "#00ff88", fontSize: 13 }}>
            {sys?.fault_count}
          </div>
        </div>
      </div>

      <MetricRow
        label="AVG Tsys"
        value={snapshot.alma.avg_tsys_k}
        unit="K"
        data={history.map((h) => h.avg_tsys_k)}
        color="#00aaff"
        min={40} max={150}
        warn={100} crit={130}
      />
      <MetricRow
        label="WIND SPEED"
        value={atm.wind_ms}
        unit="m/s"
        data={history.map((h) => h.wind_ms)}
        color="#ffaa00"
        min={0} max={35}
        warn={20} crit={25}
      />
      <MetricRow
        label="PWV"
        value={atm.pwv_mm}
        unit="mm"
        data={history.map((h) => h.pwv_mm)}
        color="#aa55ff"
        min={0} max={3}
        warn={2.0}
      />
      <MetricRow
        label="τ₂₂₅GHz"
        value={tauScaled}
        unit="mτ"
        data={history.map((h) => h.tau * 1000)}
        color="#55ddaa"
        min={20} max={60}
      />
      <MetricRow
        label="TEMPERATURE"
        value={atm.temp_c}
        unit="°C"
        data={history.map((h) => h.temp_c)}
        color="#ff8844"
        min={-20} max={5}
      />

      {/* Dishes online bar */}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid #0d1a24" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 10, color: "#556" }}>DISHES ONLINE</span>
          <span style={{ fontSize: 14, color: "#00ff88", fontWeight: "bold" }}>
            {snapshot.alma.online_count} / {snapshot.alma.total_count}
          </span>
        </div>
        <div style={{ background: "#0a141e", height: 6, borderRadius: 3 }}>
          <div style={{
            height: "100%",
            borderRadius: 3,
            background: "#00ff88",
            width: `${(snapshot.alma.online_count / snapshot.alma.total_count) * 100}%`,
            transition: "width 0.5s ease",
          }} />
        </div>
      </div>

      {/* Seeing + Humidity */}
      <div style={{ padding: "8px 12px" }}>
        <div style={{ fontSize: 10, color: "#556", marginBottom: 2 }}>SEEING</div>
        <div style={{ fontSize: 13, color: "#ccddee" }}>
          {atm.seeing_arcsec?.toFixed(2)} arcsec
        </div>
        <div style={{ fontSize: 10, color: "#334", marginTop: 2 }}>
          Humidity: {atm.humidity_pct?.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}