/**
 * auth.js  —  ATMOS client-side auth (Zustand store + React helpers)
 *
 * Integrates with the FastAPI auth.py backend.
 * Drop into client/src/stores/auth.js
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ─── Role hierarchy (mirrors Python backend) ─────────────────────────────
export const ROLES = ["viewer", "operator", "engineer", "admin"];
const ROLE_RANK = Object.fromEntries(ROLES.map((r, i) => [r, i]));

export function hasRole(userRole, minimumRole) {
  return (ROLE_RANK[userRole] ?? -1) >= (ROLE_RANK[minimumRole] ?? 99);
}

// ─── Zustand store ───────────────────────────────────────────────────────
export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,         // { username, role, full_name }
      accessToken: null,
      refreshToken: null,
      expiresAt: null,    // epoch ms
      loading: false,
      error: null,

      // ── Login ──────────────────────────────────────────────────────────
      login: async (username, password) => {
        set({ loading: true, error: null });
        try {
          const form = new URLSearchParams({ username, password });
          const res = await fetch(`${API}/auth/token`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: form,
          });
          if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail ?? "Login failed");
          }
          const data = await res.json();

          // Fetch full user profile
          const meRes = await fetch(`${API}/auth/me`, {
            headers: { Authorization: `Bearer ${data.access_token}` },
          });
          const me = await meRes.json();

          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            expiresAt: Date.now() + data.expires_in * 1000,
            user: me,
            loading: false,
            error: null,
          });
          return true;
        } catch (e) {
          set({ loading: false, error: e.message });
          return false;
        }
      },

      // ── Logout ─────────────────────────────────────────────────────────
      logout: () => {
        set({ user: null, accessToken: null, refreshToken: null, expiresAt: null });
      },

      // ── Auto-refresh before expiry ──────────────────────────────────────
      refreshIfNeeded: async () => {
        const { expiresAt, refreshToken, logout } = get();
        if (!refreshToken) return;
        // Refresh if token expires within 5 minutes
        if (expiresAt - Date.now() > 5 * 60 * 1000) return;

        try {
          const res = await fetch(`${API}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(refreshToken),
          });
          if (!res.ok) { logout(); return; }
          const data = await res.json();
          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            expiresAt: Date.now() + data.expires_in * 1000,
          });
        } catch {
          logout();
        }
      },

      // ── Helpers ────────────────────────────────────────────────────────
      isAuthenticated: () => {
        const { accessToken, expiresAt } = get();
        return !!accessToken && Date.now() < (expiresAt ?? 0);
      },
      can: (minimumRole) => {
        const { user } = get();
        return user ? hasRole(user.role, minimumRole) : false;
      },

      // ── Authenticated fetch wrapper ─────────────────────────────────────
      authFetch: async (url, options = {}) => {
        await get().refreshIfNeeded();
        const token = get().accessToken;
        return fetch(url.startsWith("http") ? url : `${API}${url}`, {
          ...options,
          headers: {
            ...options.headers,
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
      },

      // ── WebSocket URL with token ────────────────────────────────────────
      wsUrl: (path) => {
        const token = get().accessToken;
        const base = API.replace(/^http/, "ws");
        return `${base}${path}?token=${token}`;
      },
    }),
    {
      name: "atmos-auth",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        expiresAt: state.expiresAt,
        user: state.user,
      }),
    }
  )
);

// ─── React components ────────────────────────────────────────────────────

/**
 * Wrap any route that requires auth.
 * Usage: <ProtectedRoute minimumRole="operator"><Dashboard /></ProtectedRoute>
 */
export function ProtectedRoute({ children, minimumRole = "viewer", fallback = null }) {
  const { isAuthenticated, can } = useAuthStore();

  if (!isAuthenticated()) {
    return fallback ?? <LoginPrompt />;
  }
  if (!can(minimumRole)) {
    return <AccessDenied requiredRole={minimumRole} />;
  }
  return children;
}

/**
 * Conditionally render based on role.
 * Usage: <RoleGate role="engineer"><FaultInjector /></RoleGate>
 */
export function RoleGate({ children, role, fallback = null }) {
  const can = useAuthStore((s) => s.can);
  return can(role) ? children : fallback;
}

// ─── Login form ──────────────────────────────────────────────────────────
function LoginPrompt() {
  const { login, loading, error } = useAuthStore();
  const [u, setU] = React.useState("");
  const [p, setP] = React.useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(u, p);
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "#0a0e1a",
    }}>
      <div style={{
        background: "#0d1525", border: "0.5px solid #2a3a5a",
        borderRadius: 12, padding: 32, width: 340,
      }}>
        <h1 style={{ color: "#e0eaff", fontSize: 20, fontWeight: 500, margin: "0 0 4px" }}>
          ATMOS
        </h1>
        <p style={{ color: "#6080a0", fontSize: 13, margin: "0 0 24px" }}>
          Atacama Telescope Monitoring System
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 12, color: "#6080a0", marginBottom: 6 }}>
              Username
            </label>
            <input
              value={u} onChange={(e) => setU(e.target.value)}
              style={{
                width: "100%", padding: "8px 12px", background: "#0a0e1a",
                border: "0.5px solid #2a3a5a", borderRadius: 6,
                color: "#e0eaff", fontSize: 14,
              }}
              autoComplete="username"
            />
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: "block", fontSize: 12, color: "#6080a0", marginBottom: 6 }}>
              Password
            </label>
            <input
              type="password" value={p} onChange={(e) => setP(e.target.value)}
              style={{
                width: "100%", padding: "8px 12px", background: "#0a0e1a",
                border: "0.5px solid #2a3a5a", borderRadius: 6,
                color: "#e0eaff", fontSize: 14,
              }}
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p style={{ color: "#ff6060", fontSize: 12, margin: "0 0 16px" }}>⚠ {error}</p>
          )}

          <button type="submit" disabled={loading} style={{
            width: "100%", padding: "10px", background: "#1e3a6e",
            border: "0.5px solid #4080c0", borderRadius: 6,
            color: "#80c0ff", fontSize: 14, cursor: loading ? "wait" : "pointer",
          }}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div style={{ marginTop: 20, padding: "12px", background: "#0a0e1a", borderRadius: 6 }}>
          <p style={{ color: "#4060a0", fontSize: 11, margin: "0 0 6px" }}>Demo credentials:</p>
          {[["viewer", "viewer123"], ["operator", "operator123"],
            ["engineer", "engineer123"], ["admin", "admin123"]].map(([u, p]) => (
            <button key={u} onClick={() => { setU(u); setP(p); }}
              style={{
                marginRight: 6, marginBottom: 4, padding: "2px 8px", fontSize: 11,
                background: "transparent", border: "0.5px solid #2a3a5a",
                borderRadius: 4, color: "#6080a0", cursor: "pointer",
              }}>{u}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AccessDenied({ requiredRole }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: 200, color: "#6080a0", fontSize: 14,
    }}>
      ⛔ Requires <strong style={{ color: "#c0d4ff", margin: "0 4px" }}>{requiredRole}</strong> role or higher
    </div>
  );
}

import React from "react";
export { LoginPrompt };
