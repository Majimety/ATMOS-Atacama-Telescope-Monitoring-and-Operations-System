const THRESHOLDS = {
  tsys_warning_k: 100,
  tsys_critical_k: 130,
  wind_warning_ms: 20,
  wind_danger_ms: 25,
  pwv_warning_mm: 2.0,
  el_low_warning: 15,
};

const prevDishOnline = new Map();
let prevWindLevel = "ok";
let prevPwvLevel = "ok";

export function detectAlerts(snapshot) {
  const alerts = [];
  const { alma, atmosphere } = snapshot;

  for (const dish of alma.dishes) {
    const wasOnline = prevDishOnline.get(dish.id);

    if (wasOnline === undefined) {
      prevDishOnline.set(dish.id, dish.online);
      continue;
    }

    if (wasOnline && !dish.online) {
      alerts.push({
        severity: "critical",
        type: "dish_offline",
        title: `${dish.id} OFFLINE`,
        message: `Dish ${dish.id} lost contact — moved to stow position (Az 0° El 15°)`,
        dishId: dish.id,
      });
    } else if (!wasOnline && dish.online) {
      alerts.push({
        severity: "info",
        type: "dish_recovered",
        title: `${dish.id} RECOVERED`,
        message: `Dish ${dish.id} back online — telemetry nominal`,
        dishId: dish.id,
      });
    }

    prevDishOnline.set(dish.id, dish.online);

    if (dish.online && dish.tsys_k !== null) {
      if (dish.tsys_k > THRESHOLDS.tsys_critical_k) {
        alerts.push({
          severity: "critical",
          type: "tsys_critical",
          title: `${dish.id} Tsys CRITICAL`,
          message: `Tsys = ${dish.tsys_k} K — exceeds ${THRESHOLDS.tsys_critical_k} K limit. Possible receiver failure.`,
          dishId: dish.id,
        });
      } else if (dish.tsys_k > THRESHOLDS.tsys_warning_k) {
        alerts.push({
          severity: "warning",
          type: "tsys_warning",
          title: `${dish.id} Tsys HIGH`,
          message: `Tsys = ${dish.tsys_k} K (threshold: ${THRESHOLDS.tsys_warning_k} K)`,
          dishId: dish.id,
        });
      }

      if (dish.online && dish.el_deg < THRESHOLDS.el_low_warning) {
        alerts.push({
          severity: "warning",
          type: "low_elevation",
          title: `${dish.id} LOW ELEVATION`,
          message: `El = ${dish.el_deg}° — high airmass, degraded sensitivity`,
          dishId: dish.id,
        });
      }
    }
  }

  // Wind
  const windLevel =
    atmosphere.wind_ms >= THRESHOLDS.wind_danger_ms ? "danger" :
    atmosphere.wind_ms >= THRESHOLDS.wind_warning_ms ? "warning" : "ok";

  if (windLevel === "danger" && prevWindLevel !== "danger") {
    alerts.push({
      severity: "critical",
      type: "wind_danger",
      title: "WIND SPEED CRITICAL",
      message: `${atmosphere.wind_ms} m/s — exceeds safe tracking limit. STOW ALL recommended.`,
    });
  } else if (windLevel === "warning" && prevWindLevel === "ok") {
    alerts.push({
      severity: "warning",
      type: "wind_warning",
      title: "WIND SPEED ELEVATED",
      message: `${atmosphere.wind_ms} m/s — monitor closely. Limit: ${THRESHOLDS.wind_danger_ms} m/s`,
    });
  }
  prevWindLevel = windLevel;

  // PWV
  const pwvLevel = atmosphere.pwv_mm >= THRESHOLDS.pwv_warning_mm ? "high" : "ok";
  if (pwvLevel === "high" && prevPwvLevel === "ok") {
    alerts.push({
      severity: "warning",
      type: "pwv_high",
      title: "PWV ELEVATED",
      message: `PWV = ${atmosphere.pwv_mm} mm — observing conditions degraded for high-frequency bands`,
    });
  }
  prevPwvLevel = pwvLevel;

  // Fault count spike
  if (snapshot.system?.fault_count > 5) {
    alerts.push({
      severity: "critical",
      type: "mass_fault",
      title: "MULTIPLE DISH FAULTS",
      message: `${snapshot.system.fault_count} dishes offline — check array health`,
    });
  }

  return alerts;
}
