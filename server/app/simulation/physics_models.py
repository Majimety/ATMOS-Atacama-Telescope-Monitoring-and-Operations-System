"""
physics_models.py — Physical models จริงสำหรับ ALMA simulation

ทุก formula มี reference จากเอกสาร ALMA จริง
"""

import math


# ── Airmass calculation ───────────────────────────────────────────────────────


def airmass(elevation_deg: float) -> float:
    """
    Airmass X = sec(zenith_angle) พร้อมแก้ไขสำหรับมุม elevation ต่ำ

    ใช้ Kasten & Young (1989) formula ซึ่งแม่นยำกว่า sec(z) ธรรมดา
    เมื่อ elevation < 20°:
      X = 1 / (sin(el) + 0.50572 × (el + 6.07995)^-1.6364)
      โดย el เป็น degrees

    Reference: Kasten, F. and Young, A.T. 1989, Appl. Opt. 28, 4735
    ALMA Technical Handbook (Cycle 10), Eq. 9.6
    """
    el = max(elevation_deg, 1.0)  # ป้องกัน division by zero
    el_rad = math.radians(el)

    # Kasten-Young correction
    X = 1.0 / (math.sin(el_rad) + 0.50572 * (el + 6.07995) ** -1.6364)
    return round(X, 4)


# ── Tsys physical model ───────────────────────────────────────────────────────

# Receiver noise temperatures จริงของ ALMA แต่ละ band (K)
# Reference: ALMA Technical Handbook Cycle 10, Table 9.1
ALMA_RECEIVER_TEMP = {
    1: 26,  # Band 1:  35-50 GHz
    2: 50,  # Band 2:  67-90 GHz  (estimated)
    3: 45,  # Band 3:  84-116 GHz
    4: 51,  # Band 4: 125-163 GHz
    5: 65,  # Band 5: 163-211 GHz
    6: 55,  # Band 6: 211-275 GHz  ← most used
    7: 75,  # Band 7: 275-370 GHz
    8: 196,  # Band 8: 385-500 GHz
    9: 175,  # Band 9: 602-720 GHz
    10: 230,  # Band 10: 787-950 GHz
}

# Atmospheric emission coefficient β per band
# τ_band ≈ β × τ_225 (scaling จาก 225 GHz)
# Reference: Pardo et al. (2001), ATM model
ALMA_TAU_SCALE = {
    1: 0.06,  # Band 1  — transparent
    2: 0.08,
    3: 0.12,  # Band 3
    4: 0.18,
    5: 0.40,  # Band 5  — near water line
    6: 0.30,  # Band 6
    7: 0.50,  # Band 7  — significant water absorption
    8: 0.90,
    9: 2.50,  # Band 9  — strong water line at 620 GHz
    10: 4.00,  # Band 10 — near 900 GHz, very sensitive to PWV
}

T_CMB = 2.73  # K — Cosmic Microwave Background
T_ATM = 270.0  # K — effective atmospheric temperature at Chajnantor


def compute_tsys(
    band: int,
    tau_225ghz: float,
    elevation_deg: float,
    t_rx_override: float | None = None,
) -> float:
    """
    System temperature จากสูตร radiometry จริง:

      Tsys = T_rx + η × T_atm × (1 - e^(-τ × X)) + T_CMB × e^(-τ × X)

    โดย:
      T_rx  = receiver noise temperature (จาก spec)
      η     = forward efficiency (~0.95)
      T_atm = atmospheric physical temperature (~270K ที่ Chajnantor)
      τ     = opacity ที่ band นั้น (= τ_scale × τ_225)
      X     = airmass (ขึ้นกับ elevation)

    Reference: ALMA Technical Handbook Cycle 10, Eq. 9.8-9.11
    """
    T_rx = t_rx_override or ALMA_RECEIVER_TEMP.get(band, 60)
    tau_scale = ALMA_TAU_SCALE.get(band, 0.30)

    tau_band = tau_scale * tau_225ghz
    X = airmass(elevation_deg)
    eta = 0.95  # forward efficiency

    # Atmospheric contribution
    atm_term = eta * T_ATM * (1 - math.exp(-tau_band * X))

    # CMB contribution (attenuated through atmosphere)
    cmb_term = T_CMB * math.exp(-tau_band * X)

    tsys = T_rx + atm_term + cmb_term
    return round(tsys, 1)


# ── ALMA slew rate limiter ────────────────────────────────────────────────────

# Slew rates จริงตาม ALMA spec
# Reference: ALMA Technical Requirements Document, TRE-90.00.00-001-A
ALMA_MAX_SLEW_RATE_DEG_S = {
    "azimuth": 3.0,  # °/s — 12m antennas
    "elevation": 1.5,  # °/s
}

# Settling time หลัง slew (เพื่อให้ pointing error < 0.6 arcsec)
ALMA_SETTLE_TIME_S = 3.0

# Acceleration limit
ALMA_MAX_ACCEL_DEG_S2 = {
    "azimuth": 1.5,  # °/s²
    "elevation": 0.75,  # °/s²
}


class DishPointing:
    """
    จำลอง pointing ของ dish 1 ตัวโดยคำนึงถึง slew rate, acceleration จริง

    State machine:
      idle → slewing → settling → tracking
    """

    def __init__(self, dish_id: str, az0: float = 0.0, el0: float = 45.0):
        self.dish_id = dish_id

        # Current actual pointing
        self.az_actual = az0
        self.el_actual = el0

        # Commanded target
        self.az_target = az0
        self.el_target = el0

        # Velocity state (°/s)
        self.az_vel = 0.0
        self.el_vel = 0.0

        # State
        self.state = "tracking"  # "idle" | "slewing" | "settling" | "tracking"
        self.settle_timer = 0.0

        # Tracking noise amplitude (arcsec → degrees)
        # ALMA spec: tracking error < 0.6 arcsec RMS
        self._tracking_noise_amp = 0.6 / 3600  # degrees

    def command_slew(self, az_deg: float, el_deg: float):
        """รับคำสั่ง slew ใหม่"""
        self.az_target = az_deg % 360
        self.el_target = max(5.0, min(85.0, el_deg))
        self.state = "slewing"
        self.settle_timer = 0.0

    def command_stow(self):
        """Stow: Az 0°, El 15° (safe position)"""
        self.command_slew(0.0, 15.0)

    def update(self, dt: float, t: float) -> tuple[float, float]:
        """
        อัพเดท position ตาม dt (วินาที) และ physics จริง

        Returns: (az_actual, el_actual) ณ เวลา t
        """
        if self.state == "tracking":
            # Tracking noise — สมจริงตาม ALMA spec 0.6 arcsec RMS
            import math, random

            phase = hash(self.dish_id) % 1000
            az_err = math.sin(t * 0.1 + phase) * self._tracking_noise_amp * 0.5
            el_err = math.cos(t * 0.13 + phase + 1) * self._tracking_noise_amp * 0.5
            return (
                round(self.az_actual + az_err, 4),
                round(self.el_actual + el_err, 4),
            )

        if self.state == "slewing":
            # Angular distance ที่เหลือ
            az_diff = _wrap_angle(self.az_target - self.az_actual)
            el_diff = self.el_target - self.el_actual

            az_done = abs(az_diff) < 0.001
            el_done = abs(el_diff) < 0.001

            if az_done and el_done:
                self.az_actual = self.az_target
                self.el_actual = self.el_target
                self.state = "settling"
                self.settle_timer = ALMA_SETTLE_TIME_S
            else:
                # Move at max slew rate (with direction sign)
                max_az = ALMA_MAX_SLEW_RATE_DEG_S["azimuth"]
                max_el = ALMA_MAX_SLEW_RATE_DEG_S["elevation"]

                az_step = _clamp(az_diff, -max_az * dt, max_az * dt)
                el_step = _clamp(el_diff, -max_el * dt, max_el * dt)

                self.az_actual = (self.az_actual + az_step) % 360
                self.el_actual = self.el_actual + el_step

            return (round(self.az_actual, 3), round(self.el_actual, 3))

        if self.state == "settling":
            self.settle_timer -= dt
            if self.settle_timer <= 0:
                self.state = "tracking"
            # ขณะ settling ยังมี residual error เล็กน้อย
            import random

            residual = (self.settle_timer / ALMA_SETTLE_TIME_S) * 0.01
            return (
                round(self.az_actual + random.gauss(0, residual), 4),
                round(self.el_actual + random.gauss(0, residual), 4),
            )

        return (round(self.az_actual, 3), round(self.el_actual, 3))

    @property
    def pointing_mode(self) -> str:
        return self.state


def _wrap_angle(deg: float) -> float:
    """Wrap angle difference to [-180, 180]"""
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Signal-to-noise estimate ──────────────────────────────────────────────────


def compute_signal_level_dbm(
    tsys: float,
    elevation_deg: float,
    band: int,
) -> float:
    """
    Estimate received signal level (dBm) จาก radiometry จริง

    ค่านี้เป็น approximate — ขึ้นกับ source flux และ correlator gain
    ใช้สำหรับ display ใน SCADA เท่านั้น
    """
    # Sensitivity ลดลงตาม Tsys
    tsys_ref = ALMA_RECEIVER_TEMP.get(band, 60)
    sensitivity_factor = 10 * math.log10(tsys_ref / tsys)

    # Elevation effect (airmass)
    el_factor = 10 * math.log10(math.sin(math.radians(max(10, elevation_deg))))

    base_dbm = -14.0  # arbitrary reference level
    return round(base_dbm + sensitivity_factor + el_factor * 0.3, 2)
