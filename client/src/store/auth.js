/**
 * auth.js — ATMOS client-side auth store
 *
 * Supports two modes:
 *   1. Real mode  — calls FastAPI /auth/token endpoint (JWT)
 *   2. Demo mode  — validates against hardcoded demo accounts locally
 *
 * Auto-refresh:
 *   - refresh ทำงานล่วงหน้า 2 นาทีก่อน token หมดอายุ
 *   - ถ้า refresh ล้มเหลว → logout อัตโนมัติ
 *   - onRehydrateStorage → ตั้ง timer ใหม่เมื่อ reload หน้า
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// refresh ล่วงหน้า 2 นาทีก่อน token หมดอายุ
const REFRESH_BEFORE_EXPIRY_MS = 2 * 60 * 1000;

// ── Internal refresh timer (module-level — ไม่ใส่ใน Zustand state) ──────────
let _refreshTimer = null;

function _clearTimer() {
  if (_refreshTimer) {
    clearTimeout(_refreshTimer);
    _refreshTimer = null;
  }
}

function _scheduleRefresh(expiresAt, refreshFn) {
  _clearTimer();
  const delay = expiresAt - Date.now() - REFRESH_BEFORE_EXPIRY_MS;
  if (delay <= 0) {
    // token ใกล้หมดหรือหมดแล้ว — refresh ทันที
    refreshFn();
    return;
  }
  _refreshTimer = setTimeout(refreshFn, delay);
}

// ── Role hierarchy ─────────────────────────────────────────────────────────
export const ROLES = ["viewer", "operator", "engineer", "admin"];
const ROLE_RANK = Object.fromEntries(ROLES.map((r, i) => [r, i]));

export function hasRole(userRole, minimumRole) {
  return (ROLE_RANK[userRole] ?? -1) >= (ROLE_RANK[minimumRole] ?? 99);
}

// ── Demo accounts — ต้องตรงกับ server/auth.py _DEMO_USERS ────────────────
const DEMO_USERS = {
  viewer:   { username: "viewer",   role: "viewer",   full_name: "Observation Viewer",   password: "viewer123" },
  operator: { username: "operator", role: "operator", full_name: "Array Operator",        password: "operator123" },
  engineer: { username: "engineer", role: "engineer", full_name: "Systems Engineer",      password: "engineer123" },
  admin:    { username: "admin",    role: "admin",    full_name: "System Administrator",  password: "admin123" },
};

function makeDemoToken(username) {
  const payload = { sub: username, role: DEMO_USERS[username]?.role, demo: true };
  return "demo." + btoa(JSON.stringify(payload));
}

// ── Zustand store ──────────────────────────────────────────────────────────
export const useAuthStore = create(
  persist(
    (set, get) => ({
      user:         null,
      accessToken:  null,
      refreshToken: null,
      expiresAt:    null,
      loading:      false,
      error:        null,
      demoMode:     false,

      // ── Login ────────────────────────────────────────────────────────────
      login: async (username, password) => {
        set({ loading: true, error: null });

        // 1. Try real backend first
        try {
          const form = new URLSearchParams({ username, password });
          const res = await fetch(`${API}/auth/token`, {
            method:  "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body:    form,
            signal:  AbortSignal.timeout(3000),
          });

          if (res.ok) {
            const data = await res.json();
            const meRes = await fetch(`${API}/auth/me`, {
              headers: { Authorization: `Bearer ${data.access_token}` },
            });
            const me = meRes.ok ? await meRes.json() : { username, role: "viewer" };

            const expiresAt = Date.now() + (data.expires_in ?? 3600) * 1000;
            set({
              accessToken:  data.access_token,
              refreshToken: data.refresh_token ?? null,
              expiresAt,
              user:         me,
              loading:      false,
              error:        null,
              demoMode:     false,
            });

            // เริ่ม auto-refresh timer
            _scheduleRefresh(expiresAt, () => get().refresh());
            return true;
          }

          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail ?? `HTTP ${res.status}`);

        } catch (err) {
          const isNetworkError = err.name === "TypeError" || err.name === "AbortError";
          if (!isNetworkError) {
            set({ loading: false, error: err.message });
            return false;
          }
        }

        // 2. Demo mode — validate locally
        const demo = DEMO_USERS[username];
        if (demo && demo.password === password) {
          const { password: _, ...safeUser } = demo;
          const expiresAt = Date.now() + 8 * 3600 * 1000;
          set({
            user:         safeUser,
            accessToken:  makeDemoToken(username),
            refreshToken: null,
            expiresAt,
            loading:      false,
            error:        null,
            demoMode:     true,
          });
          // Demo mode ไม่ต้อง refresh — token เป็น fake และ expiresAt ยาว 8 ชม.
          return true;
        }

        set({ loading: false, error: "Invalid username or password" });
        return false;
      },

      // ── Token refresh ─────────────────────────────────────────────────────
      refresh: async () => {
        const { refreshToken, demoMode, logout } = get();

        // Demo mode ไม่มี refresh token จริง
        if (demoMode || !refreshToken) return false;

        try {
          // POST the refresh token as a JSON body.
          // The server's /auth/refresh endpoint expects application/json with
          // a { refresh_token } field, not a query parameter.
          const res = await fetch(`${API}/auth/refresh`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ refresh_token: refreshToken }),
            signal:  AbortSignal.timeout(5000),
          });

          if (!res.ok) throw new Error(`HTTP ${res.status}`);

          const data = await res.json();
          const expiresAt = Date.now() + (data.expires_in ?? 3600) * 1000;

          set({
            accessToken:  data.access_token,
            refreshToken: data.refresh_token ?? refreshToken,
            expiresAt,
          });

          // ตั้ง timer รอบถัดไป
          _scheduleRefresh(expiresAt, () => get().refresh());
          return true;

        } catch (err) {
          // refresh ล้มเหลว → logout บังคับ
          console.warn("[ATMOS Auth] Token refresh failed — logging out:", err.message);
          logout();
          return false;
        }
      },

      // ── Logout ───────────────────────────────────────────────────────────
      logout: () => {
        _clearTimer();
        set({
          user: null, accessToken: null, refreshToken: null,
          expiresAt: null, error: null, demoMode: false,
        });
      },

      // ── Token checks ─────────────────────────────────────────────────────
      isExpired: () => {
        const { expiresAt } = get();
        return expiresAt ? Date.now() > expiresAt : true;
      },

      isAuthenticated: () => {
        const { user, expiresAt } = get();
        return !!user && (expiresAt ? Date.now() < expiresAt : true);
      },

      // ── WS URL helper ─────────────────────────────────────────────────────
      // demo token ไม่ส่งไป backend — backend จะ reject
      wsUrl: (path = "/ws/telemetry") => {
        const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";
        const { accessToken, demoMode } = get();
        if (accessToken && !demoMode) {
          return `${WS_BASE}${path}?token=${encodeURIComponent(accessToken)}`;
        }
        return `${WS_BASE}${path}`;
      },
    }),
    {
      name: "atmos-auth",
      partialize: (s) => ({
        user: s.user, accessToken: s.accessToken,
        refreshToken: s.refreshToken, expiresAt: s.expiresAt,
        demoMode: s.demoMode,
      }),
      // ── Rehydrate: ตั้ง timer ใหม่เมื่อ reload หน้า ────────────────────
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const { expiresAt, demoMode, refreshToken, isAuthenticated } = state;
        if (demoMode || !refreshToken || !expiresAt) return;
        if (!isAuthenticated()) return;
        _scheduleRefresh(expiresAt, () => useAuthStore.getState().refresh());
      },
    }
  )
);