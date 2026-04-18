import { create } from "zustand";

const MAX_ALERTS = 300;

export const useAlertStore = create((set, get) => ({
  alerts: [],
  unackedCount: 0,

  push: (alert) => {
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: new Date(),
      acked: false,
      ...alert,
    };
    set((state) => {
      const alerts = [entry, ...state.alerts].slice(0, MAX_ALERTS);
      const unackedCount = alerts.filter((a) => !a.acked).length;
      return { alerts, unackedCount };
    });
  },

  ackAll: () =>
    set((state) => ({
      alerts: state.alerts.map((a) => ({ ...a, acked: true })),
      unackedCount: 0,
    })),

  clear: () => set({ alerts: [], unackedCount: 0 }),
}));
