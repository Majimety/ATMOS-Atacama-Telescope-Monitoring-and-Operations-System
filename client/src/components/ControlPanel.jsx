import { useState } from "react";

const BANDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const BAND_FREQ = { 1:43, 2:67, 3:100, 4:144, 5:183, 6:230, 7:345, 8:397, 9:650, 10:870 };

const OBS_MODES = ["interferometry", "single-dish", "vlbi", "commissioning", "maintenance"];

const TARGETS = [
  { name: "Sgr A*",    az: 183.7,  el: 52.4 },
  { name: "M87",       az: 282.5,  el: 28.1 },
  { name: "Crab",      az: 84.1,   el: 63.3 },
  { name: "Orion KL",  az: 93.2,   el: 44.7 },
  { name: "3C 273",    az: 187.3,  el: 61.2 },
];

function Label({ children }) {
  return <div style={{ fontSize: 10, color: "#556", letterSpacing: "0.08em", marginBottom: 4 }}>{children}</div>;
}

function SectionTitle({ children }) {
  return (
    <div style={{ padding: "7px 12px", borderBottom: "1px solid #0d1a24", fontSize: 11, color: "#00d4ff", letterSpacing: "0.1em" }}>
      {children}
    </div>
  );
}

export default function ControlPanel({ send, snapshot, selectedId }) {
  const [az, setAz] = useState("183.7");
  const [el, setEl] = useState("52.4");
  const [band, setBand] = useState(6);
  const [mode, setMode] = useState("interferometry");
  const [faultDishId, setFaultDishId] = useState("");

  const sys = snapshot?.system;
  const pointing = snapshot?.pointing_mode || "tracking";

  function doSlew() {
    const a = parseFloat(az);
    const e = parseFloat(el);
    if (isNaN(a) || isNaN(e)) return;
    send({ type: "slew", az: a, el: e });
  }

  function selectTarget(t) {
    setAz(t.az.toString());
    setEl(t.el.toString());
    send({ type: "slew", az: t.az, el: t.el });
  }

  function applyBand(b) {
    setBand(b);
    send({ type: "set_band", band: b });
  }

  function applyMode(m) {
    setMode(m);
    send({ type: "set_mode", mode: m });
  }

  const inputStyle = {
    background: "#050d14", border: "1px solid #1a2a3a", color: "#e0e0e0",
    fontFamily: "monospace", fontSize: 13, padding: "5px 8px",
    borderRadius: 3, width: "100%", boxSizing: "border-box",
  };

  const btnStyle = (color = "#00aaff") => ({
    background: "transparent", border: `1px solid ${color}44`,
    color, fontFamily: "monospace", fontSize: 11,
    padding: "5px 10px", cursor: "pointer", borderRadius: 3,
    width: "100%", marginTop: 4,
  });

  const pointingColor = {
    slewing: "#ffaa00", stow: "#ff8844", tracking: "#00ff88", idle: "#556",
  }[pointing] || "#556";

  return (
    <div style={{ fontFamily: "monospace", background: "#07101a", height: "100%", overflowY: "auto" }}>

      {/* Status strip */}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid #1a2a3a", display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ fontSize: 10, color: "#556" }}>STATUS</span>
        <span style={{ fontSize: 11, color: pointingColor, fontWeight: "bold", textTransform: "uppercase" }}>
          {pointing}
        </span>
        <span style={{ fontSize: 10, color: "#334", marginLeft: "auto" }}>
          AZ {snapshot?.commanded_target?.az_deg?.toFixed(1)}° EL {snapshot?.commanded_target?.el_deg?.toFixed(1)}°
        </span>
      </div>

      {/* Pointing control */}
      <SectionTitle>POINTING CONTROL</SectionTitle>
      <div style={{ padding: "10px 12px" }}>
        <Label>QUICK TARGETS</Label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 10 }}>
          {TARGETS.map((t) => (
            <button key={t.name} onClick={() => selectTarget(t)} style={{
              ...btnStyle("#4488aa"),
              fontSize: 10, padding: "4px 6px",
            }}>
              {t.name}
            </button>
          ))}
        </div>

        <Label>AZIMUTH (°)</Label>
        <input
          type="number" min="0" max="360" step="0.1"
          value={az} onChange={(e) => setAz(e.target.value)}
          style={{ ...inputStyle, marginBottom: 8 }}
        />

        <Label>ELEVATION (°)</Label>
        <input
          type="number" min="5" max="89" step="0.1"
          value={el} onChange={(e) => setEl(e.target.value)}
          style={{ ...inputStyle, marginBottom: 10 }}
        />

        <button onClick={doSlew} style={btnStyle("#00aaff")}>▶ SLEW</button>
        <button onClick={() => send({ type: "stow" })} style={{ ...btnStyle("#ff4444"), marginTop: 6 }}>
          ■ STOW ALL
        </button>
      </div>

      {/* Band selector */}
      <SectionTitle>RECEIVER BAND</SectionTitle>
      <div style={{ padding: "10px 12px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
          {BANDS.map((b) => (
            <button key={b} onClick={() => applyBand(b)} style={{
              background: (sys?.band ?? band) === b ? "#003355" : "transparent",
              border: `1px solid ${(sys?.band ?? band) === b ? "#00aaff" : "#1a2a3a"}`,
              color: (sys?.band ?? band) === b ? "#00aaff" : "#445",
              fontFamily: "monospace", fontSize: 10,
              padding: "4px 0", cursor: "pointer", borderRadius: 3,
            }}>
              B{b}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: "#aabbcc" }}>
          {BAND_FREQ[sys?.band ?? band]} GHz center
        </div>
      </div>

      {/* Obs mode */}
      <SectionTitle>OBSERVATION MODE</SectionTitle>
      <div style={{ padding: "10px 12px" }}>
        {OBS_MODES.map((m) => (
          <button key={m} onClick={() => applyMode(m)} style={{
            ...btnStyle((sys?.obs_mode ?? mode) === m ? "#00ff88" : "#334"),
            textAlign: "left", marginTop: 3, fontSize: 10,
            background: (sys?.obs_mode ?? mode) === m ? "#001a0d" : "transparent",
          }}>
            {(sys?.obs_mode ?? mode) === m ? "● " : "○ "}{m.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Fault injection */}
      <SectionTitle>FAULT INJECTION</SectionTitle>
      <div style={{ padding: "10px 12px" }}>
        <Label>DISH ID (e.g. DA-03)</Label>
        <input
          type="text"
          placeholder={selectedId || "DA-01"}
          value={faultDishId}
          onChange={(e) => setFaultDishId(e.target.value.toUpperCase())}
          style={{ ...inputStyle, marginBottom: 8 }}
        />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <button onClick={() => send({ type: "inject_fault", dish_id: faultDishId || selectedId || "DA-01", offline: true })}
            style={btnStyle("#ff4444")}>
            FORCE OFFLINE
          </button>
          <button onClick={() => send({ type: "inject_fault", dish_id: faultDishId || selectedId || "DA-01", offline: false })}
            style={btnStyle("#00ff88")}>
            RESTORE
          </button>
        </div>
      </div>
    </div>
  );
}
