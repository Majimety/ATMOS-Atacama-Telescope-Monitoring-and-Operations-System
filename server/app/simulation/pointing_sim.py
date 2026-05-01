"""
pointing_sim.py — Pointing controller สำหรับ ATMOS
"""

import math
import time

from app.simulation.physics_models import ALMA_MAX_SLEW_RATE_DEG_S, ALMA_SETTLE_TIME_S

# ดึงค่า slew rate จาก physics_models ซึ่งอ้างอิง ALMA TRE spec จริง
# az=3.0°/s, el=1.5°/s (เดิม pointing_sim ใช้ 2.0 และ 1.0 ซึ่งผิด)
SLEW_RATE_AZ_DEG_S = ALMA_MAX_SLEW_RATE_DEG_S["azimuth"]  # 3.0°/s
SLEW_RATE_EL_DEG_S = ALMA_MAX_SLEW_RATE_DEG_S["elevation"]  # 1.5°/s


class PointingController:
    """
    จำลอง telescope mount ที่ค่อยๆ หมุนไปหา target
    แทนที่จะ teleport ทันที ซึ่งไม่สมจริง

    ใช้ slew rate จาก ALMA TRE spec (physics_models.py):
      azimuth   : 3.0°/s
      elevation : 1.5°/s
    """

    def __init__(self, az_init: float = 183.7, el_init: float = 52.4):
        self.current_az = az_init
        self.current_el = el_init
        self.target_az = az_init
        self.target_el = el_init
        self._last_update = time.time()
        self.is_stowing = False
        self.mode = "tracking"  # tracking | slewing | stow | idle
        self._settle_timer = 0.0

    def command_slew(self, az: float, el: float):
        self.target_az = max(0.0, min(360.0, az))
        self.target_el = max(5.0, min(89.0, el))
        self.is_stowing = False
        self.mode = "slewing"
        self._settle_timer = 0.0

    def command_stow(self):
        self.target_az = 0.0
        self.target_el = 15.0  # stow elevation จริงของ ALMA
        self.is_stowing = True
        self.mode = "stow"
        self._settle_timer = 0.0

    def step(self) -> tuple[float, float, str]:
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        if self.mode == "settling":
            self._settle_timer -= dt
            if self._settle_timer <= 0:
                self.mode = "stow" if self.is_stowing else "tracking"
            return round(self.current_az, 3), round(self.current_el, 3), self.mode

        az_delta = self.target_az - self.current_az

        # จัดการ wrap-around ของ azimuth (เช่น 350° → 10° ควรไปทางสั้น)
        if az_delta > 180:
            az_delta -= 360
        elif az_delta < -180:
            az_delta += 360

        el_delta = self.target_el - self.current_el

        # เคลื่อนที่ตาม slew rate แต่ไม่เกิน delta ที่เหลือ
        az_move = math.copysign(min(abs(az_delta), SLEW_RATE_AZ_DEG_S * dt), az_delta)
        el_move = math.copysign(min(abs(el_delta), SLEW_RATE_EL_DEG_S * dt), el_delta)

        self.current_az = (self.current_az + az_move) % 360
        self.current_el = self.current_el + el_move

        # อัปเดต mode — เพิ่ม settling phase ตาม ALMA_SETTLE_TIME_S
        on_target = abs(az_delta) < 0.01 and abs(el_delta) < 0.01
        if on_target and self.mode == "slewing":
            self.mode = "settling"
            self._settle_timer = ALMA_SETTLE_TIME_S

        return round(self.current_az, 3), round(self.current_el, 3), self.mode


# singleton — ใช้ร่วมกันทั้ง app
controller = PointingController()
