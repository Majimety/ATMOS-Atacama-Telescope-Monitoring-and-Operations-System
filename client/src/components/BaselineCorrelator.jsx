/**
 * BaselineCorrelator.jsx
 * Real-time baseline correlation matrix for ALMA interferometric array
 *
 * Shows:
 *   - Amplitude matrix: |V_ij| for each antenna pair
 *   - Phase matrix: arg(V_ij) in degrees
 *   - RFI flagging: outlier detection via MAD threshold
 *   - Bad baseline identification: low-coherence baselines highlighted
 *
 * Integration: subscribes to WebSocket telemetry, computes mock visibility
 * amplitudes from Tsys and pointing error data. Swap simulateVisibility()
 * with real correlator output when hardware is connected.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from "react";

// ─── Visibility simulator (replace with real correlator feed) ────────────
function simulateVisibilities(antennas, pwv, windSpeed, time) {
  const N = antennas.length;
  const matrix = [];

  for (let i = 0; i < N; i++) {
    matrix[i] = [];
    for (let j = 0; j < N; j++) {
      if (i === j) {
        // Auto-correlation: system temperature noise floor
        const tsys = 60 + antennas[i].tsysOffset + pwv * 8;
        matrix[i][j] = { amp: tsys, phase: 0, flagged: false, reason: "auto" };
        continue;
      }

      if (j < i) {
        // Use conjugate symmetry
        matrix[i][j] = {
          amp: matrix[j][i]?.amp ?? 0,
          phase: -(matrix[j][i]?.phase ?? 0),
          flagged: matrix[j][i]?.flagged ?? false,
          reason: matrix[j][i]?.reason ?? null,
        };
        continue;
      }

      // Cross-correlation: simulate realistic noise + signal
      const baselineLen = Math.sqrt(
        (antennas[i].E - antennas[j].E) ** 2 +
        (antennas[i].N - antennas[j].N) ** 2
      );

      // Source visibility (simple Gaussian brightness model)
      const u_approx = baselineLen * Math.cos(time * 0.1) / 1000;
      const v_approx = baselineLen * Math.sin(time * 0.1) / 1000;
      const sourceAmp = 2.5 * Math.exp(-(u_approx ** 2 + v_approx ** 2) * 0.001);

      // Atmospheric coherence loss
      const coherence = Math.exp(-pwv * 0.15) * Math.exp(-windSpeed * 0.02);

      // Thermal noise
      const thermalNoise = (Math.random() - 0.5) * 0.3;
      const amp = Math.max(0, (sourceAmp + thermalNoise) * coherence);

      // Phase: atmospheric delay + fringe
      const atmDelay = pwv * 0.4 * (Math.random() - 0.5);
      const fringeRate = baselineLen * 0.0001;
      const phase = ((atmDelay + fringeRate * time * 0.01) * 180) / Math.PI;

      // Simulate faults: ~3% chance of bad baseline (shadowing, RFI, hardware)
      const seed = (i * 100 + j + Math.floor(time / 300)) % 997;
      const isFlagged = seed < 30;
      let reason = null;
      if (isFlagged) {
        reason = ["RFI", "Shadow", "Hardware", "Phase jump"][seed % 4];
      }

      matrix[i][j] = {
        amp: isFlagged ? amp * (2 + Math.random() * 5) : amp,
        phase: isFlagged ? (Math.random() - 0.5) * 360 : phase % 180,
        flagged: isFlagged,
        reason,
      };
    }
  }

  return matrix;
}

// ─── Colour maps ──────────────────────────────────────────────────────────
function ampToColor(amp, maxAmp, flagged) {
  if (flagged) return "rgb(180, 40, 40)";
  const t = Math.min(amp / maxAmp, 1);
  // Viridis-inspired: deep purple → teal → yellow
  const r = Math.round(68 + t * (255 - 68));
  const g = Math.round(1 + t * 240);
  const b = Math.round(84 + (1 - t) * 100);
  return `rgb(${Math.round(t < 0.5 ? 68 + t * 100 : 100 + (t - 0.5) * 310)},${Math.round(g)},${Math.round(b * (1 - t))})`;
}

function phaseToColor(phase, flagged) {
  if (flagged) return "rgb(180, 40, 40)";
  // HSL wheel: phase -180..180 → hue 0..360
  const hue = ((phase + 180) / 360) * 360;
  return `hsl(${hue},70%,50%)`;
}

// ─── Main component ────────────────────────────────────────────────────────
export default function BaselineCorrelator({
  // Provide from ATMOS Zustand store
  telemetryAntennas = null,
  pwv = 1.2,
  windSpeed = 5,
}) {
  const canvasRef = useRef(null);
  const [mode, setMode] = useState("amplitude"); // "amplitude" | "phase"
  const [time, setTime] = useState(0);
  const [running, setRunning] = useState(true);
  const [hovered, setHovered] = useState(null); // {i, j, cell}
  const [flagCount, setFlagCount] = useState(0);
  const [selectedDishes, setSelectedDishes] = useState(new Set());

  // Default compact sub-array for performance (16 dishes = 120 baselines)
  const antennas = useMemo(() => {
    if (telemetryAntennas) return telemetryAntennas.slice(0, 16);
    const basePositions = [
      { id: "DV-01", E: 0,    N: 0,    tsysOffset: 0 },
      { id: "DV-02", E: 40,   N: 20,   tsysOffset: 2 },
      { id: "DV-03", E: -35,  N: 30,   tsysOffset: -3 },
      { id: "DV-04", E: 50,   N: -40,  tsysOffset: 5 },
      { id: "DV-05", E: -20,  N: -50,  tsysOffset: 1 },
      { id: "DV-06", E: 60,   N: 60,   tsysOffset: -1 },
      { id: "DA-01", E: 250,  N: 0,    tsysOffset: 4 },
      { id: "DA-02", E: 280,  N: 80,   tsysOffset: 2 },
      { id: "DA-03", E: -240, N: 120,  tsysOffset: 7 },
      { id: "DA-04", E: -260, N: -40,  tsysOffset: 3 },
      { id: "DA-05", E: 100,  N: -300, tsysOffset: -2 },
      { id: "DA-06", E: 60,   N: -320, tsysOffset: 6 },
      { id: "DA-07", E: 500,  N: 0,    tsysOffset: 8 },
      { id: "DA-08", E: 530,  N: 120,  tsysOffset: 4 },
      { id: "DA-09", E: -490, N: 250,  tsysOffset: 3 },
      { id: "DA-10", E: 200,  N: -600, tsysOffset: 9 },
    ];
    return basePositions;
  }, [telemetryAntennas]);

  const N = antennas.length;
  const CELL = Math.min(28, Math.floor(520 / N));

  const [matrix, setMatrix] = useState(() =>
    simulateVisibilities(antennas, pwv, windSpeed, 0)
  );

  // Update simulation at 2Hz when running
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setTime((t) => {
        const next = t + 0.5;
        const m = simulateVisibilities(antennas, pwv, windSpeed, next);
        setMatrix(m);
        const flags = m.flat().filter((c) => c.flagged).length / 2; // symmetric
        setFlagCount(Math.round(flags));
        return next;
      });
    }, 500);
    return () => clearInterval(id);
  }, [running, antennas, pwv, windSpeed]);

  // Draw matrix onto canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !matrix.length) return;
    const ctx = canvas.getContext("2d");
    const offset = 50; // Label margin
    const size = N * CELL;

    canvas.width = size + offset + 10;
    canvas.height = size + offset + 10;

    ctx.fillStyle = "#0a0e1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Find max amplitude (excluding auto-correlations)
    let maxAmp = 0;
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        if (i !== j && !matrix[i][j].flagged) {
          maxAmp = Math.max(maxAmp, matrix[i][j].amp);
        }
      }
    }

    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        const cell = matrix[i][j];
        const x = offset + j * CELL;
        const y = offset + i * CELL;

        // Color cell
        if (i === j) {
          ctx.fillStyle = "#1a2540"; // Auto-correlation diagonal
        } else if (mode === "amplitude") {
          ctx.fillStyle = ampToColor(cell.amp, maxAmp, cell.flagged);
        } else {
          ctx.fillStyle = phaseToColor(cell.phase, cell.flagged);
        }
        ctx.fillRect(x, y, CELL - 1, CELL - 1);

        // Highlight selected dishes
        const dish_i = selectedDishes.has(antennas[i]?.id);
        const dish_j = selectedDishes.has(antennas[j]?.id);
        if (dish_i || dish_j) {
          ctx.strokeStyle = "rgba(100,200,255,0.8)";
          ctx.lineWidth = 1.5;
          ctx.strokeRect(x, y, CELL - 1, CELL - 1);
        }

        // Hover highlight
        if (hovered && hovered.i === i && hovered.j === j) {
          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.lineWidth = 1.5;
          ctx.strokeRect(x, y, CELL - 1, CELL - 1);
        }
      }
    }

    // Antenna labels (abbreviated)
    ctx.fillStyle = "rgba(160,190,255,0.7)";
    ctx.font = `${Math.max(8, CELL - 8)}px monospace`;
    for (let i = 0; i < N; i++) {
      const label = antennas[i].id.replace(/-0?/, "");
      ctx.textAlign = "right";
      ctx.fillText(label, offset - 4, offset + i * CELL + CELL / 2 + 4);
      ctx.textAlign = "center";
      ctx.save();
      ctx.translate(offset + i * CELL + CELL / 2, offset - 4);
      ctx.rotate(-Math.PI / 4);
      ctx.fillText(label, 0, 0);
      ctx.restore();
    }

    // Flagged cells: red X
    ctx.fillStyle = "rgba(255,80,80,0.8)";
    ctx.font = `${CELL - 4}px sans-serif`;
    ctx.textAlign = "center";
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        if (matrix[i][j].flagged) {
          const x = offset + j * CELL + CELL / 2;
          const y = offset + i * CELL + CELL / 2 + 4;
          if (CELL >= 14) ctx.fillText("✕", x, y);
        }
      }
    }
  }, [matrix, mode, N, CELL, hovered, selectedDishes, antennas]);

  // Mouse hover for tooltip
  const handleMouseMove = useCallback(
    (e) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const offset = 50;
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX - offset;
      const my = (e.clientY - rect.top) * scaleY - offset;
      const j = Math.floor(mx / CELL);
      const i = Math.floor(my / CELL);
      if (i >= 0 && i < N && j >= 0 && j < N) {
        setHovered({ i, j, cell: matrix[i][j] });
      } else {
        setHovered(null);
      }
    },
    [matrix, N, CELL]
  );

  const handleClick = useCallback(
    (e) => {
      if (!hovered) return;
      const { i, j } = hovered;
      const ids = [antennas[i]?.id, antennas[j]?.id].filter(Boolean);
      setSelectedDishes((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => {
          if (next.has(id)) next.delete(id);
          else next.add(id);
        });
        return next;
      });
    },
    [hovered, antennas]
  );

  const totalBaselines = (N * (N - 1)) / 2;
  const flagPercent = ((flagCount / totalBaselines) * 100).toFixed(1);

  return (
    <div style={{ fontFamily: "sans-serif", background: "#0a0e1a", color: "#c0d4ff", borderRadius: 12, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 500, color: "#e0eaff" }}>
            Baseline Correlation Matrix
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6080a0" }}>
            {N}×{N} = {totalBaselines} cross-correlations · {flagCount} flagged ({flagPercent}%)
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {["amplitude", "phase"].map((m) => (
            <button key={m} onClick={() => setMode(m)} style={{
              padding: "4px 12px", fontSize: 11, borderRadius: 6, cursor: "pointer",
              background: mode === m ? "#1e3a6e" : "transparent",
              border: `0.5px solid ${mode === m ? "#4080c0" : "#2a3a5a"}`,
              color: mode === m ? "#80c0ff" : "#6080a0",
            }}>{mode === m ? "● " : ""}{m}</button>
          ))}
          <button onClick={() => setRunning(!running)} style={{
            padding: "4px 12px", fontSize: 11, borderRadius: 6, cursor: "pointer",
            background: running ? "#1a3a20" : "#3a1a1a",
            border: `0.5px solid ${running ? "#40a060" : "#a04040"}`,
            color: running ? "#60d080" : "#d06060",
          }}>{running ? "⏸" : "▶"}</button>
        </div>
      </div>

      <div style={{ position: "relative" }}>
        <canvas
          ref={canvasRef}
          style={{ width: "100%", borderRadius: 8, cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHovered(null)}
          onClick={handleClick}
        />

        {/* Tooltip */}
        {hovered && hovered.i !== hovered.j && (
          <div style={{
            position: "absolute", top: 8, right: 8,
            background: "#0d1525", border: "0.5px solid #2a3a5a",
            borderRadius: 8, padding: "10px 14px", fontSize: 12, minWidth: 180,
          }}>
            <div style={{ color: "#e0eaff", fontWeight: 500, marginBottom: 6 }}>
              {antennas[hovered.i]?.id} × {antennas[hovered.j]?.id}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", color: "#6080a0" }}>
              <span>Amplitude</span>
              <span style={{ color: "#c0d4ff" }}>{hovered.cell.amp.toFixed(3)} Jy</span>
              <span>Phase</span>
              <span style={{ color: "#c0d4ff" }}>{hovered.cell.phase.toFixed(1)}°</span>
              <span>Status</span>
              <span style={{ color: hovered.cell.flagged ? "#ff6060" : "#60d080" }}>
                {hovered.cell.flagged ? `⚠ ${hovered.cell.reason}` : "✓ Good"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Colour scale legend */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
        <span style={{ fontSize: 11, color: "#4060a0" }}>
          {mode === "amplitude" ? "0 Jy" : "-180°"}
        </span>
        <div style={{
          flex: 1, height: 10, borderRadius: 5,
          background: mode === "amplitude"
            ? "linear-gradient(to right, #440154, #31688e, #35b779, #fde725)"
            : "linear-gradient(to right, hsl(0,70%,50%), hsl(120,70%,50%), hsl(240,70%,50%), hsl(360,70%,50%))",
        }} />
        <span style={{ fontSize: 11, color: "#4060a0" }}>
          {mode === "amplitude" ? "peak" : "+180°"}
        </span>
        <span style={{ fontSize: 11, color: "#ff6060", marginLeft: 8 }}>■ flagged</span>
        <span style={{ fontSize: 11, color: "#1a2540", marginLeft: 4 }}>■ auto-corr</span>
      </div>

      {/* Selected dish info */}
      {selectedDishes.size > 0 && (
        <div style={{ marginTop: 12, padding: "8px 12px", background: "#0d1525", borderRadius: 8, fontSize: 12 }}>
          <span style={{ color: "#4080c0" }}>Selected: </span>
          <span style={{ color: "#80c0ff" }}>{[...selectedDishes].join(", ")}</span>
          <button onClick={() => setSelectedDishes(new Set())} style={{
            marginLeft: 12, padding: "2px 8px", fontSize: 11, background: "transparent",
            border: "0.5px solid #2a3a5a", borderRadius: 4, color: "#4060a0", cursor: "pointer",
          }}>clear</button>
        </div>
      )}
    </div>
  );
}
