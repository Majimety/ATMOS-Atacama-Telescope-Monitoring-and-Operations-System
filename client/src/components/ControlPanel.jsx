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
  return (
    <div style={{
      fontSize: 11,
      color: "#6688aa",
      letterSpacing: "0.05em",
      marginBottom: 6,
      fontWeight: "600",
    }}>
      {children}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <div style={{
      padding: "10px 16px",
      borderBottom: "1px solid #0d1a24",
      fontSize: 12,
      color: "#00d4ff",
      letterSpacing: "0.12em",
      fontWeight: "600",
      background: "#050d14",
    }}>
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
    background: "#050d14",
    border: "1px solid #1a2a3a",
    color: "#e0e0e0",
    fontFamily: "monospace",
    fontSize: 14,
    padding: "8px 12px",
    borderRadius: 4,
    width: "100%",
    boxSizing: "border-box",
    outline: "none",
    transition: "border-color 0.2s ease",
  };

  const btnStyle = (color = "#00aaff", variant = "outline") => ({
    background: variant === "solid" ? color : "transparent",
    border: `1px solid ${color}`,
    color: variant === "solid" ? "#fff" : color,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: "600",
    padding: "9px 14px",
    cursor: "pointer",
    borderRadius: 4,
    width: "100%",
    marginTop: 6,
    transition: "all 0.2s ease",
    letterSpacing: "0.05em",
  });

  const pointingColor = {
    slewing: "#ffaa00",
    stow: "#ff8844",
    tracking: "#00ff88",
    idle: "#6688aa",
  }[pointing] || "#6688aa";

  return (
    <div style={{
      fontFamily: "monospace",
      background: "#07101a",
      height: "100%",
      overflowY: "auto",
    }}>

      {/* Status strip */}
      <div style={{
        padding: "12px 16px",
        borderBottom: "1px solid #1a2a3a",
        display: "flex",
        gap: 14,
        alignItems: "center",
        background: "#050d14",
      }}>
        <span style={{
          fontSize: 11,
          color: "#6688aa",
          fontWeight: "600",
        }}>
          STATUS
        </span>
        <span style={{
          fontSize: 12,
          color: pointingColor,
          fontWeight: "bold",
          textTransform: "uppercase",
        }}>
          {pointing}
        </span>
        <div style={{
          marginLeft: "auto",
          fontSize: 11,
          color: "#445566",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          lineHeight: 1.4,
        }}>
          <div>AZ {snapshot?.commanded_target?.az_deg?.toFixed(1)}°</div>
          <div>EL {snapshot?.commanded_target?.el_deg?.toFixed(1)}°</div>
        </div>
      </div>

      {/* Pointing control */}
      <SectionTitle>POINTING CONTROL</SectionTitle>
      <div style={{ padding: "14px 16px" }}>
        <Label>QUICK TARGETS</Label>
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 6,
          marginBottom: 14,
        }}>
          {TARGETS.map((t) => (
            <button
              key={t.name}
              onClick={() => selectTarget(t)}
              style={{
                background: "transparent",
                border: "1px solid #3a5566",
                color: "#6699bb",
                fontFamily: "monospace",
                fontSize: 11,
                fontWeight: "500",
                padding: "7px 8px",
                cursor: "pointer",
                borderRadius: 4,
                transition: "all 0.2s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "#1a2a3a";
                e.currentTarget.style.borderColor = "#00aaff";
                e.currentTarget.style.color = "#00d4ff";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.borderColor = "#3a5566";
                e.currentTarget.style.color = "#6699bb";
              }}
            >
              {t.name}
            </button>
          ))}
        </div>

        <Label>AZIMUTH (°)</Label>
        <input
          type="number"
          min="0"
          max="360"
          step="0.1"
          value={az}
          onChange={(e) => setAz(e.target.value)}
          style={{ ...inputStyle, marginBottom: 12 }}
          onFocus={(e) => e.currentTarget.style.borderColor = "#00aaff"}
          onBlur={(e) => e.currentTarget.style.borderColor = "#1a2a3a"}
        />

        <Label>ELEVATION (°)</Label>
        <input
          type="number"
          min="5"
          max="89"
          step="0.1"
          value={el}
          onChange={(e) => setEl(e.target.value)}
          style={{ ...inputStyle, marginBottom: 14 }}
          onFocus={(e) => e.currentTarget.style.borderColor = "#00aaff"}
          onBlur={(e) => e.currentTarget.style.borderColor = "#1a2a3a"}
        />

        <button
          onClick={doSlew}
          style={btnStyle("#00aaff", "outline")}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#00aaff";
            e.currentTarget.style.color = "#fff";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "#00aaff";
          }}
        >
          ▶ SLEW
        </button>
        
        <button
          onClick={() => send({ type: "stow" })}
          style={btnStyle("#ff4444", "outline")}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#ff4444";
            e.currentTarget.style.color = "#fff";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "#ff4444";
          }}
        >
          ■ STOW ALL
        </button>
      </div>

      {/* Band selector */}
      <SectionTitle>RECEIVER BAND</SectionTitle>
      <div style={{ padding: "14px 16px" }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)",
          gap: 6,
        }}>
          {BANDS.map((b) => {
            const isActive = (sys?.band ?? band) === b;
            return (
              <button
                key={b}
                onClick={() => applyBand(b)}
                style={{
                  background: isActive ? "#003355" : "transparent",
                  border: `1px solid ${isActive ? "#00aaff" : "#2a3a4a"}`,
                  color: isActive ? "#00d4ff" : "#6688aa",
                  fontFamily: "monospace",
                  fontSize: 11,
                  fontWeight: isActive ? "bold" : "500",
                  padding: "6px 0",
                  cursor: "pointer",
                  borderRadius: 4,
                  transition: "all 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.borderColor = "#4a6a7a";
                    e.currentTarget.style.color = "#88aacc";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.borderColor = "#2a3a4a";
                    e.currentTarget.style.color = "#6688aa";
                  }
                }}
              >
                B{b}
              </button>
            );
          })}
        </div>
        <div style={{
          marginTop: 12,
          fontSize: 12,
          color: "#aabbcc",
          textAlign: "center",
          padding: "8px",
          background: "#0a141e",
          borderRadius: 4,
        }}>
          <span style={{ color: "#00d4ff", fontWeight: "600" }}>
            {BAND_FREQ[sys?.band ?? band]} GHz
          </span>
          <span style={{ color: "#556677", marginLeft: 6 }}>center</span>
        </div>
      </div>

      {/* Obs mode */}
      <SectionTitle>OBSERVATION MODE</SectionTitle>
      <div style={{ padding: "14px 16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {OBS_MODES.map((m) => {
            const isActive = (sys?.mode ?? mode) === m;
            return (
              <button
                key={m}
                onClick={() => applyMode(m)}
                style={{
                  background: isActive ? "#1a2a3a" : "transparent",
                  border: `1px solid ${isActive ? "#00aaff" : "#2a3a4a"}`,
                  color: isActive ? "#00d4ff" : "#6688aa",
                  fontFamily: "monospace",
                  fontSize: 11,
                  fontWeight: isActive ? "600" : "500",
                  padding: "8px 12px",
                  cursor: "pointer",
                  borderRadius: 4,
                  textAlign: "left",
                  transition: "all 0.2s ease",
                  textTransform: "capitalize",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = "#0d1a24";
                    e.currentTarget.style.borderColor = "#3a5566";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.borderColor = "#2a3a4a";
                  }
                }}
              >
                {m}
              </button>
            );
          })}
        </div>
      </div>

      {/* Emergency controls */}
      <SectionTitle>EMERGENCY</SectionTitle>
      <div style={{ padding: "14px 16px" }}>
        <Label>INJECT FAULT (TESTING)</Label>
        <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
          <input
            type="text"
            placeholder="Dish ID (e.g. DA-45)"
            value={faultDishId}
            onChange={(e) => setFaultDishId(e.target.value)}
            style={{ ...inputStyle, flex: 1, fontSize: 12 }}
            onFocus={(e) => e.currentTarget.style.borderColor = "#00aaff"}
            onBlur={(e) => e.currentTarget.style.borderColor = "#1a2a3a"}
          />
          <button
            onClick={() => {
              if (faultDishId.trim()) {
                send({ type: "inject_fault", dishId: faultDishId.trim() });
                setFaultDishId("");
              }
            }}
            style={{
              ...btnStyle("#ffaa00", "outline"),
              width: "auto",
              padding: "8px 14px",
              marginTop: 0,
              fontSize: 11,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "#ffaa00";
              e.currentTarget.style.color = "#fff";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "#ffaa00";
            }}
          >
            INJECT
          </button>
        </div>

        <button
          onClick={() => send({ type: "emergency_stop" })}
          style={{
            ...btnStyle("#ff3333", "solid"),
            fontWeight: "bold",
            fontSize: 13,
            marginTop: 12,
          }}
        >
          ⚠ EMERGENCY STOP
        </button>
      </div>

      {/* Spacer */}
      <div style={{ height: 20 }} />
    </div>
  );
}