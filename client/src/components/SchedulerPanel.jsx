import { useTelemetryStore } from "../store/telemetryStore";
import { useAuthStore, hasRole } from "../store/auth";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const PRIORITY_META = {
  0: { label: "URGENT", color: "#ff4444", bg: "#130404" },
  1: { label: "HIGH",   color: "#ff8844", bg: "#130b04" },
  2: { label: "NORMAL", color: "#00aaff", bg: "#00070d" },
  3: { label: "LOW",    color: "#445566", bg: "#070c12" },
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
      <div style={{ color: "#1a2d3d", fontSize: 18, marginBottom: 6 }}>◌</div>
      <div style={{ color: "#1e3344", fontSize: 10, letterSpacing: "0.1em" }}>NO ACTIVE OBSERVATION</div>
      <div style={{ color: "#152535", fontSize: 9, marginTop: 3 }}>Scheduler awaiting conditions</div>
    </div>
  );

  const pct = job.progress_pct;

  return (
    <div style={S.activeJob}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{ minWidth: 0, flex: 1, marginRight: 8 }}>
          <div style={{ fontSize: 14, color: "#00ff88", fontWeight: 700, letterSpacing: "0.04em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {job.target_name}
          </div>
          <div style={{ fontSize: 9, color: "#334d5c", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {job.ra}&nbsp;&nbsp;{job.dec}
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 11, color: BAND_COLORS[job.band] ?? "#00d4ff", fontWeight: 700 }}>B{job.band}</div>
          <div style={{ fontSize: 9, color: "#334d5c", marginTop: 2 }}>{fmtDuration(job.duration_s)}</div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={S.progressTrack}>
        <div style={{ ...S.progressFill, width: `${pct}%` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9, color: "#334d5c" }}>
        <span>{fmtElapsed(job.elapsed_s)} elapsed</span>
        <span style={{ color: "#00aa66" }}>{pct.toFixed(1)}%</span>
        <span>{fmtDuration(Math.max(0, job.duration_s - job.elapsed_s))} remaining</span>
      </div>

      {/* Notes */}
      {job.notes && (
        <div style={{ fontSize: 9, color: "#2a3d4d", marginTop: 6, fontStyle: "italic", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
      {/* Index */}
      <div style={{ width: 22, textAlign: "center", flexShrink: 0, fontSize: 10, color: "#2a3d4d" }}>
        #{index + 1}
      </div>

      {/* Priority badge */}
      <div style={{ ...S.badge, color: pm.color, borderColor: pm.color + "44", width: 44, flexShrink: 0 }}>
        {pm.label}
      </div>

      {/* Target info — flex:1 + minWidth:0 ทำให้ ellipsis ทำงาน */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: "#99bbcc", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {job.target_name}
        </div>
        <div style={{ fontSize: 9, color: "#2a3d4d", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          B{job.band} · {fmtDuration(job.duration_s)}
          {job.max_pwv_mm < 3 && <span style={{ color: "#2a4d55" }}> · PWV&lt;{job.max_pwv_mm}mm</span>}
          {job.skip_reason && <span style={{ color: "#554400" }}> · {job.skip_reason}</span>}
        </div>
      </div>

      {/* Controls */}
      {canControl && (
        <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
          <button style={S.iconBtn} onClick={() => onMoveUp(job.job_id)} title="Move up">▲</button>
          <button style={S.iconBtn} onClick={() => onMoveDown(job.job_id)} title="Move down">▼</button>
          <button style={{ ...S.iconBtn, color: "#cc3333" }} onClick={() => onRemove(job.job_id)} title="Remove">✕</button>
        </div>
      )}
    </div>
  );
}

function HistoryRow({ job }) {
  const sm = STATUS_META[job.status] ?? STATUS_META.completed;

  return (
    <div style={S.historyRow}>
      <div style={{ ...S.badge, color: sm.color, borderColor: sm.color + "33", width: 52, flexShrink: 0 }}>
        {sm.label}
      </div>
      <div style={{ flex: 1, minWidth: 0, fontSize: 10, color: "#445566", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {job.target_name}
      </div>
      <div style={{ fontSize: 9, color: "#2a3d4d", flexShrink: 0 }}>B{job.band}</div>
      <div style={{ fontSize: 9, color: "#2a3d4d", flexShrink: 0, minWidth: 36, textAlign: "right" }}>
        {fmtElapsed(job.elapsed_s)}
      </div>
    </div>
  );
}

// ── Add-job catalogue ─────────────────────────────────────────────────────────

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
    <div>
      <div style={S.sectionHeader}>ADD FROM CATALOGUE</div>
      <div style={S.quickGrid}>
        {QUICK_TARGETS.map((t) => (
          <button key={t.target_name} style={S.quickBtn} onClick={() => submitQuick(t)}>
            <div style={{ color: "#6aabda", fontSize: 10, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {t.target_name}
            </div>
            <div style={{ color: "#2a3d4d", fontSize: 9, marginTop: 2 }}>
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
      <div style={{ padding: 20, color: "#1e3344", fontSize: 11, textAlign: "center" }}>
        Connecting…
      </div>
    </div>
  );

  const { active, queue, history, stats } = sched;

  return (
    <div style={S.wrap}>

      {/* ── Status bar: QUEUED / COMPLETED / SKIPPED / SKIP — single row ── */}
      <div style={S.statusBar}>
        <div style={S.statChip}>
          <span style={{ color: "#2a4455" }}>QUEUED</span>
          <span style={{ color: "#00aaff", fontWeight: 700 }}>{stats.queued}</span>
        </div>
        <div style={S.statChip}>
          <span style={{ color: "#2a4455" }}>COMPLETED</span>
          <span style={{ color: "#00ff88", fontWeight: 700 }}>{stats.completed}</span>
        </div>
        <div style={S.statChip}>
          <span style={{ color: "#2a4455" }}>SKIPPED</span>
          <span style={{ color: "#ffaa00", fontWeight: 700 }}>{stats.skipped}</span>
        </div>
        {/* SKIP button — marginLeft:auto ดัน ไปชิดขวา */}
        {active && canControl && (
          <button style={S.skipBtn} onClick={skipActive}>&#9632; SKIP</button>
        )}
      </div>

      {/* ── Active observation (fixed, ไม่ scroll) ── */}
      <div style={S.sectionHeader}>ACTIVE OBSERVATION</div>
      <div style={S.activeWrap}>
        <ActiveJob job={active} />
      </div>

      {/* ── Scrollable: Queue + Catalogue + History ── */}
      <div style={S.scrollArea}>

        <div style={S.sectionHeader}>QUEUE ({queue.length})</div>
        {queue.length === 0 ? (
          <div style={{ padding: "12px", color: "#152535", fontSize: 10, textAlign: "center" }}>
            Queue empty
          </div>
        ) : (
          queue.map((job, i) => (
            <QueueRow
              key={job.job_id}
              job={job}
              index={i}
              canControl={canControl}
              onRemove={removeJob}
              onMoveUp={(id) => moveJob(id, -1)}
              onMoveDown={(id) => moveJob(id, 1)}
            />
          ))
        )}

        {canControl && <AddJobForm onAdded={() => {}} />}

        {history.length > 0 && (
          <>
            <div style={S.sectionHeader}>RECENT HISTORY</div>
            {history.slice().reverse().map((j) => (
              <HistoryRow key={j.job_id + j.completed_at} job={j} />
            ))}
          </>
        )}

        <div style={{ height: 12 }} />
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  // root: flex column, overflow hidden — child scrollArea จัดการ scroll เอง
  wrap: {
    fontFamily:    "monospace",
    background:    "#07101a",
    height:        "100%",
    overflow:      "hidden",
    color:         "#b0c8d8",
    display:       "flex",
    flexDirection: "column",
  },

  // ── Status bar: single row, ไม่ wrap, height คงที่ 30px ─────────────────
  statusBar: {
    display:      "flex",
    alignItems:   "center",
    gap:          4,
    padding:      "0 8px",
    height:       30,
    borderBottom: "1px solid #0c1820",
    background:   "#040c12",
    flexShrink:   0,
    flexWrap:     "nowrap",     // บังคับบรรทัดเดียว
    overflow:     "hidden",
  },
  statChip: {
    display:      "flex",
    gap:          4,
    alignItems:   "center",
    fontSize:     9,
    letterSpacing:"0.04em",
    padding:      "2px 5px",
    border:       "1px solid #0c1820",
    borderRadius: 2,
    whiteSpace:   "nowrap",
    flexShrink:   0,
  },
  skipBtn: {
    marginLeft:   "auto",
    background:   "transparent",
    border:       "1px solid #993333",
    color:        "#cc4444",
    fontFamily:   "monospace",
    fontSize:     9,
    padding:      "2px 8px",
    cursor:       "pointer",
    letterSpacing:"0.06em",
    whiteSpace:   "nowrap",
    flexShrink:   0,
  },

  // ── Section headers (sticky inside scrollArea) ────────────────────────────
  sectionHeader: {
    padding:      "5px 10px",
    borderBottom: "1px solid #0c1820",
    borderTop:    "1px solid #0c1820",
    fontSize:     9,
    color:        "#00c4ee",
    letterSpacing:"0.1em",
    fontWeight:   600,
    background:   "#040c12",
    flexShrink:   0,
    position:     "sticky",
    top:          0,
    zIndex:       1,
  },

  // ── Active job ────────────────────────────────────────────────────────────
  activeWrap: { flexShrink: 0 },
  emptyActive: {
    padding:   "16px 12px",
    textAlign: "center",
  },
  activeJob: {
    padding:      "10px 12px",
    borderBottom: "1px solid #0c1820",
  },
  progressTrack: {
    height:      4,
    background:  "#08151e",
    border:      "1px solid #0a2030",
    borderRadius: 1,
    overflow:    "hidden",
    marginTop:   8,
  },
  progressFill: {
    height:     "100%",
    background: "linear-gradient(90deg, #002233, #008855)",
    transition: "width 1s linear",
  },

  // ── Scrollable area ───────────────────────────────────────────────────────
  scrollArea: {
    flex:           1,
    overflowY:      "auto",
    overflowX:      "hidden",
    minHeight:      0,
    scrollbarWidth: "thin",
    scrollbarColor: "#0c2030 #040c12",
  },

  // ── Queue rows ────────────────────────────────────────────────────────────
  queueRow: {
    display:      "flex",
    alignItems:   "center",
    gap:          5,
    padding:      "5px 8px",
    borderBottom: "1px solid #09131c",
  },
  badge: {
    fontSize:      9,
    fontWeight:    700,
    letterSpacing: "0.05em",
    padding:       "1px 4px",
    border:        "1px solid",
    textAlign:     "center",
    flexShrink:    0,
    borderRadius:  2,
  },
  iconBtn: {
    background:  "transparent",
    border:      "1px solid #0c1e2a",
    color:       "#2a3d4d",
    fontFamily:  "monospace",
    fontSize:    10,
    padding:     "1px 4px",
    cursor:      "pointer",
    lineHeight:  1,
  },

  // ── History rows ──────────────────────────────────────────────────────────
  historyRow: {
    display:      "flex",
    alignItems:   "center",
    gap:          6,
    padding:      "4px 8px",
    borderBottom: "1px solid #070f16",
    opacity:      0.7,
  },

  // ── Add-job catalogue ─────────────────────────────────────────────────────
  quickGrid: {
    display:             "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap:                 1,
    background:          "#040c12",
  },
  quickBtn: {
    background:   "#060f18",
    border:       "none",
    borderBottom: "1px solid #09131c",
    padding:      "7px 9px",
    textAlign:    "left",
    cursor:       "pointer",
    fontFamily:   "monospace",
    overflow:     "hidden",
  },
};