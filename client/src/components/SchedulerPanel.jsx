import { useMemo } from "react";
import { useTelemetryStore } from "../store/telemetryStore";
import { useAuthStore, hasRole } from "../store/auth";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const PRIORITY_META = {
  0: { label: "URGENT", color: "#ff4444", bg: "#1a0505" },
  1: { label: "HIGH",   color: "#ff8844", bg: "#1a0c05" },
  2: { label: "NORMAL", color: "#00aaff", bg: "#00080f" },
  3: { label: "LOW",    color: "#445566", bg: "#070d14" },
};

const STATUS_META = {
  queued:    { color: "#445566", label: "QUEUED" },
  running:   { color: "#00ff88", label: "RUNNING" },
  completed: { color: "#00aaff", label: "DONE" },
  failed:    { color: "#ff4444", label: "FAILED" },
  skipped:   { color: "#ffaa00", label: "SKIPPED" },
};

const BAND_COLORS = {
  3: "#66aaff", 6: "#00d4ff", 7: "#ffaa00", 9: "#ff6644", 10: "#ff4488",
};

function fmtDuration(s) {
  if (s >= 3600) return `${(s / 3600).toFixed(1)}h`;
  if (s >= 60)   return `${Math.round(s / 60)}m`;
  return `${s}s`;
}

function fmtElapsed(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ActiveJob({ job }) {
  if (!job) return (
    <div style={S.emptyActive}>
      <div style={{ color: "#223344", fontSize: 22, marginBottom: 8 }}>◌</div>
      <div style={{ color: "#223344", fontSize: 11, letterSpacing: "0.08em" }}>NO ACTIVE OBSERVATION</div>
      <div style={{ color: "#1a2a34", fontSize: 10, marginTop: 4 }}>Scheduler awaiting conditions</div>
    </div>
  );

  const pct = job.progress_pct;
  const pm  = PRIORITY_META[job.priority] ?? PRIORITY_META[2];

  return (
    <div style={S.activeJob}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 15, color: "#00ff88", fontWeight: 700, letterSpacing: "0.05em" }}>
            {job.target_name}
          </div>
          <div style={{ fontSize: 10, color: "#445566", marginTop: 2 }}>
            {job.ra}  {job.dec}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: BAND_COLORS[job.band] ?? "#00d4ff" }}>
            B{job.band}
          </div>
          <div style={{ fontSize: 10, color: "#445566", marginTop: 2 }}>
            {fmtDuration(job.duration_s)}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={S.progressTrack}>
        <div style={{ ...S.progressFill, width: `${pct}%` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "#445566" }}>
        <span>{fmtElapsed(job.elapsed_s)} elapsed</span>
        <span>{pct.toFixed(1)}%</span>
        <span>{fmtDuration(job.duration_s - job.elapsed_s)} remaining</span>
      </div>

      {/* Notes */}
      {job.notes && (
        <div style={{ fontSize: 10, color: "#334455", marginTop: 8, fontStyle: "italic" }}>
          {job.notes}
        </div>
      )}
    </div>
  );
}

function QueueRow({ job, index, onRemove, onMoveUp, onMoveDown, canControl }) {
  const pm = PRIORITY_META[job.priority] ?? PRIORITY_META[2];

  return (
    <div style={{ ...S.queueRow, background: pm.bg }}>
      {/* Index + priority */}
      <div style={{ width: 28, textAlign: "center", flexShrink: 0 }}>
        <div style={{ fontSize: 11, color: "#334455" }}>#{index + 1}</div>
      </div>

      {/* Priority badge */}
      <div style={{ ...S.badge, color: pm.color, borderColor: pm.color + "44", width: 48 }}>
        {pm.label}
      </div>

      {/* Target info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: "#aabbcc", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {job.target_name}
        </div>
        <div style={{ fontSize: 9, color: "#334455", marginTop: 1 }}>
          B{job.band} · {fmtDuration(job.duration_s)}
          {job.max_pwv_mm < 3 && <span style={{ color: "#335566" }}> · PWV&lt;{job.max_pwv_mm}mm</span>}
        </div>
      </div>

      {/* Skip reason */}
      {job.skip_reason && (
        <div style={{ fontSize: 9, color: "#554400", maxWidth: 100, textAlign: "right", lineHeight: 1.3 }}>
          {job.skip_reason}
        </div>
      )}

      {/* Controls */}
      {canControl && (
        <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
          <button style={S.iconBtn} onClick={() => onMoveUp(job.job_id)} title="Move up">▲</button>
          <button style={S.iconBtn} onClick={() => onMoveDown(job.job_id)} title="Move down">▼</button>
          <button style={{ ...S.iconBtn, color: "#ff4444" }} onClick={() => onRemove(job.job_id)} title="Remove">✕</button>
        </div>
      )}
    </div>
  );
}

function HistoryRow({ job }) {
  const sm = STATUS_META[job.status] ?? STATUS_META.completed;
  const pm = PRIORITY_META[job.priority] ?? PRIORITY_META[2];

  return (
    <div style={S.historyRow}>
      <div style={{ ...S.badge, color: sm.color, borderColor: sm.color + "33", width: 56 }}>
        {sm.label}
      </div>
      <div style={{ flex: 1, fontSize: 11, color: "#556677" }}>{job.target_name}</div>
      <div style={{ fontSize: 10, color: "#334455" }}>B{job.band}</div>
      <div style={{ fontSize: 10, color: "#334455", minWidth: 40, textAlign: "right" }}>
        {fmtElapsed(job.elapsed_s)}
      </div>
    </div>
  );
}

// ── Add-job form ──────────────────────────────────────────────────────────────

const QUICK_TARGETS = [
  { target_name:"Sgr A*",     ra:"17h45m40s", dec:"-29°00'28\"", az:183.7, el:52.4, band:6, duration_s:3600 },
  { target_name:"M87",        ra:"12h30m49s", dec:"+12°23'28\"", az:282.5, el:28.1, band:3, duration_s:7200 },
  { target_name:"Orion KL",   ra:"05h35m14s", dec:"-05°22'30\"", az:93.2,  el:44.7, band:6, duration_s:1800 },
  { target_name:"3C 273",     ra:"12h29m06s", dec:"+02°03'08\"", az:187.3, el:61.2, band:7, duration_s:2700 },
  { target_name:"Crab Nebula",ra:"05h34m31s", dec:"+22°00'52\"", az:84.1,  el:63.3, band:3, duration_s:5400 },
];

function AddJobForm({ onAdded }) {
  const token = useAuthStore((s) => s.accessToken);

  async function submitQuick(tgt) {
    const res = await fetch(`${API}/api/scheduler/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ ...tgt, priority: 2, max_pwv_mm: 3.0, min_el_deg: 15.0 }),
    });
    if (res.ok) onAdded?.();
  }

  return (
    <div style={S.addForm}>
      <div style={S.sectionHeader}>ADD FROM CATALOGUE</div>
      <div style={S.quickGrid}>
        {QUICK_TARGETS.map((t) => (
          <button key={t.target_name} style={S.quickBtn} onClick={() => submitQuick(t)}>
            <div style={{ color: "#7abbe8", fontSize: 11, fontWeight: 600 }}>{t.target_name}</div>
            <div style={{ color: "#334455", fontSize: 9, marginTop: 2 }}>
              B{t.band} · {fmtDuration(t.duration_s)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SchedulerPanel() {
  const snapshot   = useTelemetryStore((s) => s.snapshot);
  const userRole   = useAuthStore((s) => s.user?.role ?? "viewer");
  const token      = useAuthStore((s) => s.accessToken);
  const canControl = hasRole(userRole, "operator");

  const sched = snapshot?.scheduler;

  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  async function removeJob(id) {
    await fetch(`${API}/api/scheduler/jobs/${id}`, { method: "DELETE", headers });
  }

  async function moveJob(id, dir) {
    await fetch(`${API}/api/scheduler/jobs/${id}/move?direction=${dir}`, { method: "POST", headers });
  }

  async function skipActive() {
    await fetch(`${API}/api/scheduler/skip`, { method: "POST", headers });
  }

  if (!sched) return (
    <div style={S.wrap}>
      <div style={S.sectionHeader}>OBSERVATION SCHEDULER</div>
      <div style={{ padding: 24, color: "#223344", fontSize: 12, textAlign: "center" }}>
        Connecting to scheduler…
      </div>
    </div>
  );

  const { active, queue, history, stats } = sched;

  return (
    <div style={S.wrap}>

      {/* ── Status bar ── */}
      <div style={S.statusBar}>
        <div style={S.statChip}>
          <span style={{ color: "#334455" }}>QUEUED</span>
          <span style={{ color: "#00aaff", fontWeight: 700 }}>{stats.queued}</span>
        </div>
        <div style={S.statChip}>
          <span style={{ color: "#334455" }}>COMPLETED</span>
          <span style={{ color: "#00ff88", fontWeight: 700 }}>{stats.completed}</span>
        </div>
        <div style={S.statChip}>
          <span style={{ color: "#334455" }}>SKIPPED</span>
          <span style={{ color: "#ffaa00", fontWeight: 700 }}>{stats.skipped}</span>
        </div>
        {active && canControl && (
          <button style={S.skipBtn} onClick={skipActive}>■ SKIP</button>
        )}
      </div>

      {/* ── Active observation ── */}
      <div style={S.sectionHeader}>ACTIVE OBSERVATION</div>
      <ActiveJob job={active} />

      {/* ── Queue ── */}
      <div style={S.sectionHeader}>
        QUEUE ({queue.length})
      </div>
      <div style={S.queueList}>
        {queue.length === 0 && (
          <div style={{ padding: "16px 12px", color: "#1a2a34", fontSize: 11, textAlign: "center" }}>
            Queue empty — add observations below
          </div>
        )}
        {queue.map((job, i) => (
          <QueueRow
            key={job.job_id}
            job={job}
            index={i}
            canControl={canControl}
            onRemove={removeJob}
            onMoveUp={(id) => moveJob(id, -1)}
            onMoveDown={(id) => moveJob(id, 1)}
          />
        ))}
      </div>

      {/* ── Add job ── */}
      {canControl && <AddJobForm onAdded={() => {}} />}

      {/* ── History ── */}
      {history.length > 0 && (
        <>
          <div style={S.sectionHeader}>RECENT HISTORY</div>
          <div>
            {history.slice().reverse().map((j) => (
              <HistoryRow key={j.job_id + j.completed_at} job={j} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  wrap: {
    fontFamily:  "monospace",
    background:  "#07101a",
    height:      "100%",
    overflowY:   "auto",
    color:       "#c0d4e0",
    display:     "flex",
    flexDirection: "column",
  },
  statusBar: {
    display:      "flex",
    alignItems:   "center",
    gap:          8,
    padding:      "6px 12px",
    borderBottom: "1px solid #0d1a24",
    background:   "#050d14",
    flexShrink:   0,
  },
  statChip: {
    display: "flex", gap: 5, alignItems: "center",
    fontSize: 10, letterSpacing: "0.06em",
    padding: "2px 8px", border: "1px solid #0d1a24", borderRadius: 2,
  },
  skipBtn: {
    marginLeft:  "auto",
    background:  "transparent",
    border:      "1px solid #ff4444",
    color:       "#ff4444",
    fontFamily:  "monospace",
    fontSize:    10,
    padding:     "3px 10px",
    cursor:      "pointer",
    letterSpacing: "0.08em",
  },
  sectionHeader: {
    padding:      "7px 12px",
    borderBottom: "1px solid #0d1a24",
    borderTop:    "1px solid #0d1a24",
    fontSize:     10,
    color:        "#00d4ff",
    letterSpacing: "0.1em",
    fontWeight:   600,
    background:   "#050d14",
    flexShrink:   0,
  },
  emptyActive: {
    padding:     "24px 12px",
    textAlign:   "center",
    flexShrink:  0,
  },
  activeJob: {
    padding:     "14px 14px",
    borderBottom: "1px solid #0d1a24",
    flexShrink:  0,
  },
  progressTrack: {
    height:      6,
    background:  "#0a1a24",
    border:      "1px solid #0d2535",
    borderRadius: 1,
    overflow:    "hidden",
    marginTop:   10,
  },
  progressFill: {
    height:      "100%",
    background:  "linear-gradient(90deg, #003344, #00aa66)",
    transition:  "width 1s linear",
  },
  queueList:  { flexShrink: 0 },
  queueRow: {
    display:      "flex",
    alignItems:   "center",
    gap:          8,
    padding:      "7px 10px",
    borderBottom: "1px solid #0a141e",
  },
  badge: {
    fontSize:     9,
    fontWeight:   700,
    letterSpacing: "0.08em",
    padding:      "2px 5px",
    border:       "1px solid",
    textAlign:    "center",
    flexShrink:   0,
  },
  iconBtn: {
    background:  "transparent",
    border:      "1px solid #0d2030",
    color:       "#334455",
    fontFamily:  "monospace",
    fontSize:    10,
    padding:     "2px 5px",
    cursor:      "pointer",
    lineHeight:  1,
  },
  historyRow: {
    display:      "flex",
    alignItems:   "center",
    gap:          8,
    padding:      "5px 10px",
    borderBottom: "1px solid #080f16",
    opacity:      0.75,
  },
  addForm: { flexShrink: 0 },
  quickGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap: 1,
    background: "#050d14",
  },
  quickBtn: {
    background:  "#07101a",
    border:      "none",
    borderBottom: "1px solid #0a141e",
    padding:     "9px 12px",
    textAlign:   "left",
    cursor:      "pointer",
    fontFamily:  "monospace",
  },
};
