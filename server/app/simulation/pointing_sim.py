import math
import time


# ความเร็ว slew ของ ALMA จริงอยู่ที่ ~2 deg/s สำหรับ azimuth
SLEW_RATE_AZ_DEG_S = 2.0
SLEW_RATE_EL_DEG_S = 1.0


class PointingController:
    """
    จำลอง telescope mount ที่ค่อยๆ หมุนไปหา target
    แทนที่จะ teleport ทันที ซึ่งไม่สมจริง
    """

    def __init__(self, az_init: float = 183.7, el_init: float = 52.4):
        self.current_az = az_init
        self.current_el = el_init
        self.target_az = az_init
        self.target_el = el_init
        self._last_update = time.time()
        self.is_stowing = False
        self.mode = "tracking"  # tracking | slewing | stow | idle

    def command_slew(self, az: float, el: float):
        self.target_az = max(0.0, min(360.0, az))
        self.target_el = max(5.0, min(89.0, el))
        self.is_stowing = False
        self.mode = "slewing"

    def command_stow(self):
        self.target_az = 0.0
        self.target_el = 15.0  # stow elevation จริงของ ALMA
        self.is_stowing = True
        self.mode = "stow"

    def step(self) -> tuple[float, float, str]:
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

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

        # อัปเดต mode
        on_target = abs(az_delta) < 0.01 and abs(el_delta) < 0.01
        if on_target:
            self.mode = "stow" if self.is_stowing else "tracking"

        return round(self.current_az, 3), round(self.current_el, 3), self.mode


# singleton — ใช้ร่วมกันทั้ง app
controller = PointingController()
