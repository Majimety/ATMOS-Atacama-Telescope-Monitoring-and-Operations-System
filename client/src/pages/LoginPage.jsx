import { useState, useEffect } from "react";
import { useAuthStore } from "../store/auth";

// ── Design: Mission-control dark terminal aesthetic ───────────────────────────
// Monospaced, amber-on-black, CRT scanline feel — matches ATMOS dashboard

const DEMO_ACCOUNTS = [
  { username: "viewer",   password: "viewer123",   role: "viewer",   label: "Read-only" },
  { username: "operator", password: "operator123", role: "operator", label: "Control" },
  { username: "admin",    password: "admin123",    role: "admin",    label: "Full access" },
];

const ROLE_COLOR = {
  viewer:   "#00d4ff",
  operator: "#00ff88",
  engineer: "#ffaa00",
  admin:    "#ff6644",
};

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [tick, setTick]         = useState(0);

  const login   = useAuthStore((s) => s.login);
  const loading = useAuthStore((s) => s.loading);
  const error   = useAuthStore((s) => s.error);

  // Blinking cursor tick
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 530);
    return () => clearInterval(id);
  }, []);

  async function handleSubmit(e) {
    e?.preventDefault();
    const ok = await login(username, password);
    if (ok) onLogin?.();
  }

  function fillDemo(acc) {
    setUsername(acc.username);
    setPassword(acc.password);
  }

  const cursor = tick % 2 === 0 ? "█" : " ";

  return (
    <div style={styles.root}>
      {/* Scanline overlay */}
      <div style={styles.scanlines} />

      {/* Centre card */}
      <div style={styles.card}>

        {/* Logo / header */}
        <div style={styles.logoWrap}>
          <div style={styles.logoLine}>
            <span style={styles.logoBracket}>[</span>
            <span style={styles.logoText}> ATMOS </span>
            <span style={styles.logoBracket}>]</span>
          </div>
          <div style={styles.logoSub}>
            ATACAMA TELESCOPE MONITORING AND OPERATIONS SYSTEM
          </div>
          <div style={styles.logoSub2}>v0.3.0 — SECURE TERMINAL</div>
        </div>

        {/* Divider */}
        <div style={styles.divider}>{"─".repeat(42)}</div>

        {/* Form */}
        <div style={styles.field}>
          <label style={styles.label}>USERNAME</label>
          <div style={styles.inputWrap}>
            <span style={styles.prompt}>$ </span>
            <input
              style={styles.input}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              autoFocus
              autoComplete="username"
              spellCheck={false}
            />
            {username === "" && <span style={styles.cursorSpan}>{cursor}</span>}
          </div>
        </div>

        <div style={styles.field}>
          <label style={styles.label}>PASSWORD</label>
          <div style={styles.inputWrap}>
            <span style={styles.prompt}>$ </span>
            <input
              style={styles.input}
              type={showPass ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              autoComplete="current-password"
            />
            <button
              style={styles.eyeBtn}
              onClick={() => setShowPass((v) => !v)}
              tabIndex={-1}
            >
              {showPass ? "HIDE" : "SHOW"}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={styles.error}>
            ⚠ {error}
          </div>
        )}

        {/* Submit */}
        <button
          style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "AUTHENTICATING…" : "► AUTHENTICATE"}
        </button>

        {/* Divider */}
        <div style={{ ...styles.divider, marginTop: 20 }}>
          {"─".repeat(18)} DEMO ACCOUNTS {"─".repeat(18)}
        </div>

        {/* Demo account quick-fill */}
        <div style={styles.demoGrid}>
          {DEMO_ACCOUNTS.map((acc) => (
            <button
              key={acc.username}
              style={styles.demoBtn(acc.role)}
              onClick={() => fillDemo(acc)}
            >
              <div style={{ color: ROLE_COLOR[acc.role], fontWeight: 700, fontSize: 11 }}>
                {acc.username.toUpperCase()}
              </div>
              <div style={{ color: "#445566", fontSize: 10, marginTop: 2 }}>
                {acc.label}
              </div>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div style={styles.footer}>
          CHAJNANTOR PLATEAU · 5058 m ASL · −23.019° −67.753°
        </div>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
  root: {
    position:        "fixed",
    inset:           0,
    background:      "#010a0f",
    display:         "flex",
    alignItems:      "center",
    justifyContent:  "center",
    fontFamily:      "'Courier New', 'Lucida Console', monospace",
    zIndex:          9999,
  },
  scanlines: {
    position:        "fixed",
    inset:           0,
    backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.12) 2px, rgba(0,0,0,0.12) 4px)",
    pointerEvents:   "none",
    zIndex:          1,
  },
  card: {
    position:        "relative",
    zIndex:          2,
    width:           460,
    padding:         "36px 40px 28px",
    background:      "#020d15",
    border:          "1px solid #0d3050",
    boxShadow:       "0 0 40px rgba(0,180,255,0.06), 0 0 0 1px #0a2030",
    color:           "#c8dde8",
  },
  logoWrap: { textAlign: "center", marginBottom: 24 },
  logoLine: { display: "flex", justifyContent: "center", alignItems: "baseline", gap: 4, marginBottom: 6 },
  logoBracket: { color: "#005580", fontSize: 28, fontWeight: "bold" },
  logoText:    { color: "#00aadd", fontSize: 28, fontWeight: "bold", letterSpacing: "0.35em" },
  logoSub:     { fontSize: 10, color: "#2a4a5a", letterSpacing: "0.12em", marginTop: 4 },
  logoSub2:    { fontSize: 9,  color: "#1a3040", letterSpacing: "0.1em",  marginTop: 2 },
  divider:     { color: "#0d2535", fontSize: 10, textAlign: "center", margin: "0 0 20px" },
  field:       { marginBottom: 16 },
  label:       { display: "block", fontSize: 9, color: "#335566", letterSpacing: "0.15em", marginBottom: 6 },
  inputWrap:   {
    display:         "flex",
    alignItems:      "center",
    background:      "#010a10",
    border:          "1px solid #0d2535",
    padding:         "8px 10px",
    gap:             4,
  },
  prompt:  { color: "#005a7a", fontSize: 13, flexShrink: 0 },
  input:   {
    flex:            1,
    background:      "transparent",
    border:          "none",
    outline:         "none",
    color:           "#aaddee",
    fontFamily:      "inherit",
    fontSize:        13,
    caretColor:      "#00aadd",
  },
  cursorSpan: { color: "#00aadd", fontSize: 13, userSelect: "none" },
  eyeBtn: {
    background:      "transparent",
    border:          "none",
    color:           "#224455",
    fontFamily:      "inherit",
    fontSize:        9,
    cursor:          "pointer",
    letterSpacing:   "0.08em",
    flexShrink:      0,
  },
  error: {
    background:      "#1a0505",
    border:          "1px solid #440000",
    color:           "#ff6655",
    fontSize:        11,
    padding:         "8px 12px",
    marginBottom:    12,
    letterSpacing:   "0.05em",
  },
  submitBtn: {
    width:           "100%",
    background:      "transparent",
    border:          "1px solid #006688",
    color:           "#00aacc",
    fontFamily:      "inherit",
    fontSize:        12,
    fontWeight:      "bold",
    letterSpacing:   "0.12em",
    padding:         "12px",
    cursor:          "pointer",
    marginTop:       4,
    transition:      "all 0.15s",
  },
  demoGrid: {
    display:         "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap:             8,
    marginTop:       12,
  },
  demoBtn: (role) => ({
    background:      "#010a10",
    border:          `1px solid ${ROLE_COLOR[role]}22`,
    padding:         "8px 6px",
    cursor:          "pointer",
    textAlign:       "center",
    transition:      "border-color 0.15s",
    fontFamily:      "inherit",
  }),
  footer: {
    marginTop:       24,
    textAlign:       "center",
    fontSize:        8,
    color:           "#0d2030",
    letterSpacing:   "0.1em",
  },
};
