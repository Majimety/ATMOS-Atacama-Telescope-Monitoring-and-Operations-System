import { useTelemetryStore } from "../store/telemetryStore";
import { useTelescopeStore } from "../store/telescopeStore";

const S = {
  wrap: {
    fontFamily: "monospace",
    background: "#07101a",
    height: "100%",
    overflowY: "auto",
    color: "#c0d4e0",
  },
  header: {
    padding: "8px 12px",
    borderBottom: "1px solid #1a2a3a",
    fontSize: 12,
    color: "#00d4ff",
    letterSpacing: "0.1em",
    fontWeight: 600,
    background: "#050d14",
  },
  stat: {
    padding: "10px 14px",
    borderBottom: "1px solid #0d1a24",
  },
  statLabel: { fontSize: 10, color: "#556677", letterSpacing: "0.08em", marginBottom: 3 },
  statValue: { fontSize: 15, fontWeight: "bold" },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 0,
  },
};

function Stat({ label, value, color }) {
  return (
    <div style={S.stat}>
      <div style={S.statLabel}>{label}</div>
      <div style={{ ...S.statValue, color: color || "#e0e0e0" }}>{value ?? "—"}</div>
    </div>
  );
}

export default function Dashboard() {
  const snapshot = useTelemetryStore((s) => s.snapshot);
  const selectedId = useTelescopeStore((s) => s.selectedId);
  const getSelectedDish = useTelescopeStore((s) => s.getSelectedDish);

  if (!snapshot) {
    return (
      <div style={S.wrap}>
        <div style={S.header}>SYSTEM STATUS</div>
        <div style={{ padding: 20, color: "#334455", fontSize: 12 }}>
          Connecting to telemetry stream…
        </div>
      </div>
    );
  }

  const sys = snapshot.system;
  const atm = snapshot.atmosphere;
  const alma = snapshot.alma;
  // FIX: target fields อยู่ใน commanded_target ไม่ใช่ system
  const target = snapshot.commanded_target ?? {};
  const selectedDish = getSelectedDish(snapshot);

  const onlinePct = alma.total_count > 0
    ? ((alma.online_count / alma.total_count) * 100).toFixed(1)
    : "0.0";

  return (
    <div style={S.wrap}>
      <div style={S.header}>SYSTEM STATUS</div>

      <div style={S.grid}>
        <Stat label="ONLINE DISHES" value={`${alma.online_count} / ${alma.total_count}`} color="#00ff88" />
        <Stat label="ARRAY HEALTH" value={`${onlinePct}%`} color={parseFloat(onlinePct) > 90 ? "#00ff88" : "#ffaa00"} />
        <Stat label="OBS BAND" value={`B${sys.band} · ${sys.freq_ghz} GHz`} color="#00d4ff" />
        <Stat label="MODE" value={sys.obs_mode.toUpperCase()} />
        <Stat label="AVG Tsys" value={`${alma.avg_tsys_k?.toFixed(1)} K`} color={alma.avg_tsys_k > 100 ? "#ffaa00" : "#e0e0e0"} />
        <Stat label="POINTING" value={snapshot.pointing_mode?.toUpperCase()} color={{ tracking: "#00ff88", slewing: "#ffaa00", stow: "#ff8844" }[snapshot.pointing_mode]} />
      </div>

      <div style={S.header}>ATMOSPHERE</div>
      <div style={S.grid}>
        <Stat label="PWV" value={`${atm.pwv_mm?.toFixed(2)} mm`} color={atm.pwv_mm > 2 ? "#ff8844" : "#e0e0e0"} />
        <Stat label="τ₂₂₅GHz" value={atm.tau_225ghz?.toFixed(4)} />
        <Stat label="WIND" value={`${atm.wind_ms?.toFixed(1)} m/s`} color={atm.wind_ms > 25 ? "#ff4444" : atm.wind_ms > 20 ? "#ffaa00" : "#e0e0e0"} />
        <Stat label="TEMP" value={`${atm.temp_c?.toFixed(1)} °C`} />
        <Stat label="HUMIDITY" value={`${atm.humidity_pct?.toFixed(1)}%`} />
        <Stat label="SOURCE" value={atm.source?.toUpperCase()} color={atm.source === "live" ? "#00ff88" : "#778899"} />
      </div>

      <div style={S.header}>TARGET</div>
      <div style={S.stat}>
        <div style={S.statLabel}>NAME</div>
        <div style={{ ...S.statValue, fontSize: 13, color: "#00d4ff" }}>{target.name}</div>
      </div>
      <div style={S.grid}>
        <Stat label="RA" value={target.ra} />
        <Stat label="DEC" value={target.dec} />
      </div>

      {selectedDish && (
        <>
          <div style={{ ...S.header, color: "#00ffcc" }}>SELECTED: {selectedDish.id}</div>
          <div style={S.grid}>
            <Stat label="STATUS" value={selectedDish.online ? "ONLINE" : "OFFLINE"} color={selectedDish.online ? "#00ff88" : "#ff4444"} />
            <Stat label="TYPE" value={selectedDish.ant_type} />
            <Stat label="Tsys" value={selectedDish.tsys_k ? `${selectedDish.tsys_k.toFixed(1)} K` : "—"} color={selectedDish.tsys_k > 130 ? "#ff4444" : selectedDish.tsys_k > 100 ? "#ffaa00" : "#e0e0e0"} />
            <Stat label="SIGNAL" value={selectedDish.signal_dbm ? `${selectedDish.signal_dbm.toFixed(1)} dBm` : "—"} />
            <Stat label="AZ" value={`${selectedDish.az_deg?.toFixed(2)}°`} />
            <Stat label="EL" value={`${selectedDish.el_deg?.toFixed(2)}°`} />
          </div>
        </>
      )}
    </div>
  );
}