/**
 * auth.js — ATMOS client-side auth store
 *
 * Supports two modes:
 *   1. Real mode  — calls FastAPI /auth/token endpoint (JWT)
 *   2. Demo mode  — validates against hardcoded demo accounts locally
 *                   (used when backend auth isn't fully wired up yet)
 *
 * Demo accounts (match server/auth.py _DEMO_USERS):
 *   viewer   / viewer123   → read-only
 *   operator / operator123 → control
 *   admin    / admin123    → full access
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Role hierarchy ─────────────────────────────────────────────────────────
export const ROLES = ["viewer", "operator", "engineer", "admin"];
const ROLE_RANK = Object.fromEntries(ROLES.map((r, i) => [r, i]));

export function hasRole(userRole, minimumRole) {
  return (ROLE_RANK[userRole] ?? -1) >= (ROLE_RANK[minimumRole] ?? 99);
}

// ── Demo accounts ──────────────────────────────────────────────────────────
const DEMO_USERS = {
  viewer:   { username: "viewer",   role: "viewer",   full_name: "Read-Only User",    password: "viewer123" },
  operator: { username: "operator", role: "operator", full_name: "Observatory Operator", password: "operator123" },
  admin:    { username: "admin",    role: "admin",    full_name: "System Administrator", password: "admin123" },
};

function makeDemoToken(username) {
  // Not a real JWT — just a base64 payload for demo purposes
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

            set({
              accessToken:  data.access_token,
              refreshToken: data.refresh_token ?? null,
              expiresAt:    Date.now() + (data.expires_in ?? 3600) * 1000,
              user:         me,
              loading:      false,
              error:        null,
              demoMode:     false,
            });
            return true;
          }
          // Backend returned error (wrong password etc)
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail ?? `HTTP ${res.status}`);

        } catch (err) {
          // 2. If backend unreachable → fall through to demo mode
          const isNetworkError = err.name === "TypeError" || err.name === "AbortError";
          if (!isNetworkError) {
            set({ loading: false, error: err.message });
            return false;
          }
        }

        // 3. Demo mode — validate locally
        const demo = DEMO_USERS[username];
        if (demo && demo.password === password) {
          const { password: _, ...safeUser } = demo;
          set({
            user:        safeUser,
            accessToken: makeDemoToken(username),
            refreshToken: null,
            expiresAt:   Date.now() + 8 * 3600 * 1000,
            loading:     false,
            error:       null,
            demoMode:    true,
          });
          return true;
        }

        set({ loading: false, error: "Invalid username or password" });
        return false;
      },

      // ── Logout ───────────────────────────────────────────────────────────
      logout: () => set({
        user: null, accessToken: null, refreshToken: null,
        expiresAt: null, error: null, demoMode: false,
      }),

      // ── Token check ──────────────────────────────────────────────────────
      isExpired: () => {
        const { expiresAt } = get();
        return expiresAt ? Date.now() > expiresAt : true;
      },

      isAuthenticated: () => {
        const { user, expiresAt } = get();
        return !!user && (expiresAt ? Date.now() < expiresAt : true);
      },
    }),
    {
      name:    "atmos-auth",
      partialize: (s) => ({
        user: s.user, accessToken: s.accessToken,
        refreshToken: s.refreshToken, expiresAt: s.expiresAt,
        demoMode: s.demoMode,
      }),
    }
  )
);
