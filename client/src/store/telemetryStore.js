import { create } from "zustand";

const HISTORY_LENGTH = 120; // 2 minutes at 1Hz

export const useTelemetryStore = create((set) => ({
  snapshot: null,
  history: [], // array ของ { t, avg_tsys_k, pwv_mm, wind_ms, online_count }
  lastUpdated: null,

  setSnapshot: (data) =>
    set((state) => {
      const point = {
        t: new Date(data.timestamp),
        avg_tsys_k: data.alma.avg_tsys_k,
        pwv_mm: data.atmosphere.pwv_mm,
        wind_ms: data.atmosphere.wind_ms,
        temp_c: data.atmosphere.temp_c,
        online_count: data.alma.online_count,
        tau: data.atmosphere.tau_225ghz,
      };

      const history = [...state.history, point].slice(-HISTORY_LENGTH);

      return { snapshot: data, history, lastUpdated: new Date() };
    }),
}));
