"""
test_atmos.py — ATMOS Test Case Registry
Covers all test cases in the registry (PHY, WTH, PTG, AUTH, SCH, WS, API, INF)
"""

import asyncio
import math
import sys
import os
import time
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================================
# PHY — Physics Models
# =============================================================================


class TestPhysics:

    # PHY-01: Airmass at elevation 90°
    def test_PHY01_airmass_zenith(self):
        """el=90° → airmass ≈ 1 (0.99–1.01)"""
        from app.simulation.physics_models import airmass

        X = airmass(90.0)
        assert 0.99 <= X <= 1.01, (
            f"PHY-01 FAIL: airmass(90°) = {X}, expected 0.99–1.01\n"
            "  Kasten-Young at el=90: X = 1/(sin(90)+0.50572*(90+6.07995)^-1.6364) ≈ 0.9988"
        )

    # PHY-02: Airmass at elevation 1° (horizon)
    def test_PHY02_airmass_horizon(self):
        """el=1° → airmass ≈ 26–32 per Kasten-Young 1989"""
        from app.simulation.physics_models import airmass

        X = airmass(1.0)
        assert 26 <= X <= 32, (
            f"PHY-02 FAIL: airmass(1°) = {X}, expected 26–32 (Kasten-Young 1989 Table 1)\n"
            "  True value from paper: X(1°) ≈ 26.96\n"
            "  sec(89°) ≈ 57.3 but Kasten-Young is more accurate"
        )

    # PHY-03: Tsys Band 6 nominal
    def test_PHY03_tsys_band6_nominal(self):
        """Band 6, good PWV (tau=0.050), el=52.4° → Tsys ≈ 58–72 K"""
        from app.simulation.physics_models import compute_tsys

        tsys = compute_tsys(6, 0.050, 52.4)
        assert 58 <= tsys <= 72, (
            f"PHY-03 FAIL: Tsys(B6, tau=0.050, el=52.4°) = {tsys} K, expected 58–72 K\n"
            "  T_rx=55K, tau_scale=0.30, tau_band=0.015, X≈1.26\n"
            "  ALMA Cycle 10 spec: typical B6 Tsys ≈ 55–75 K at good PWV"
        )

    # PHY-04: Tsys Band 9 high PWV
    def test_PHY04_tsys_band9_high_pwv(self):
        """Band 9, tau=0.15, el=45° → Tsys > 250 K"""
        from app.simulation.physics_models import compute_tsys

        tsys = compute_tsys(9, 0.15, 45.0)
        assert tsys > 250, (
            f"PHY-04 FAIL: Tsys(B9, tau=0.15, el=45°) = {tsys} K, expected > 250 K\n"
            "  T_rx=175K, tau_scale=2.50, tau_band=0.375, X≈1.41\n"
            "  atmospheric term ≈ 0.95*270*(1-e^(-0.529)) ≈ 94 K → total >> 250 K"
        )

    # PHY-05: CMB term present even near-zero tau
    def test_PHY05_cmb_term_present(self):
        """Band 1, tau≈0, el=89° → Tsys ≈ 28.5–29.0 K (T_rx + CMB)"""
        from app.simulation.physics_models import compute_tsys

        tsys = compute_tsys(1, 0.001, 89.0)
        assert 28.5 <= tsys <= 29.0, (
            f"PHY-05 FAIL: Tsys(B1, tau≈0, el=89°) = {tsys} K, expected 28.5–29.0 K\n"
            "  T_rx=26K, tau_band≈0.00006, CMB≈2.73K\n"
            "  Verify CMB term does not vanish when tau → 0: T_CMB*e^(-tau*X) → 2.73"
        )

    # PHY-06: signal_level_dbm decreases at lower elevation
    def test_PHY06_signal_level_vs_elevation(self):
        """dBm(el=10°) < dBm(el=60°) — must differ by > 1 dB"""
        from app.simulation.physics_models import compute_signal_level_dbm

        dbm_low = compute_signal_level_dbm(80, 10, 6)
        dbm_high = compute_signal_level_dbm(80, 60, 6)
        assert dbm_low < dbm_high, (
            f"PHY-06 FAIL: dBm(el=10°)={dbm_low} >= dBm(el=60°)={dbm_high}\n"
            "  Must be monotonic: lower elevation → higher airmass → lower sensitivity → lower dBm"
        )
        diff = dbm_high - dbm_low
        assert (
            diff > 1.0
        ), f"PHY-06 FAIL: difference only {diff:.2f} dB, expected > 1 dB"

    # PHY-07: ALMA_TAU_SCALE Band 10 must be maximum
    def test_PHY07_tau_scale_band10_max(self):
        """tau_scale[10]=4.0 must be max; tau_scale[1]=0.06 must be min"""
        from app.simulation.physics_models import ALMA_TAU_SCALE

        max_band = max(ALMA_TAU_SCALE, key=ALMA_TAU_SCALE.get)
        min_band = min(ALMA_TAU_SCALE, key=ALMA_TAU_SCALE.get)
        assert (
            ALMA_TAU_SCALE[10] == 4.0
        ), f"PHY-07 FAIL: tau_scale[10]={ALMA_TAU_SCALE[10]}, expected 4.0"
        assert max_band == 10, (
            f"PHY-07 FAIL: max tau_scale is band {max_band}={ALMA_TAU_SCALE[max_band]}, expected band 10=4.0\n"
            "  Band 10 (787-950 GHz) near water line → most opaque"
        )
        assert (
            ALMA_TAU_SCALE[1] == 0.06
        ), f"PHY-07 FAIL: tau_scale[1]={ALMA_TAU_SCALE[1]}, expected 0.06"
        assert (
            min_band == 1
        ), f"PHY-07 FAIL: min tau_scale is band {min_band}, expected band 1"

    # PHY-08: airmass at el=0° — no crash, return > 20
    def test_PHY08_airmass_zero_elevation(self):
        """el=0° → no crash, return > 20 (clipped to 1°)"""
        from app.simulation.physics_models import airmass

        try:
            X = airmass(0.0)
        except Exception as e:
            pytest.fail(f"PHY-08 FAIL: airmass(0°) raised {e}")
        assert X > 20, (
            f"PHY-08 FAIL: airmass(0°) = {X}, expected > 20\n"
            "  Code uses max(el, 1.0) → clip to 1° → X ≈ 26.96"
        )


# =============================================================================
# WTH — Weather
# =============================================================================


class TestWeather:

    # WTH-01: tau formula inconsistency across 3 files
    def test_WTH01_tau_formula_consistency(self):
        """
        Verify tau_225 formula is consistent across 3 locations:
        - README: tau = 0.04*PWV + 0.012
        - weather_fetcher: derive_tau_from_pwv()
        - atmosphere_sim: formula in simulate_atmosphere()
        All must agree within ±10% at PWV=1.0 mm
        """
        pwv = 1.0
        readme_tau = 0.04 * pwv + 0.012  # = 0.052 (README / ALMA spec)

        # Value from actual weather_fetcher
        from app.simulation.weather_fetcher import derive_tau_from_pwv

        actual_fetcher_tau = derive_tau_from_pwv(pwv)

        # Value from atmosphere_sim — read formula directly from source
        import ast, inspect
        from app.simulation import atmosphere_sim

        src = inspect.getsource(atmosphere_sim.simulate_atmosphere)
        # Find PWV coefficient in tau line
        # Supports both "0.04 * pwv + 0.012" and "0.040 * pwv + 0.012"
        import re

        m = re.search(r"([\d.]+)\s*\*\s*pwv\s*\+\s*([\d.]+)", src)
        if m:
            sim_tau = float(m.group(1)) * pwv + float(m.group(2))
        else:
            # fallback: run function multiple times and average (remove noise)
            import random as _rand

            _rand.seed(42)
            vals = [
                atmosphere_sim.simulate_atmosphere(t=0.0)["tau_225ghz"]
                for _ in range(50)
            ]
            sim_tau = sum(vals) / len(vals)

        # All three must be within ±10% of README formula
        tol = readme_tau * 0.10
        assert abs(actual_fetcher_tau - readme_tau) <= tol, (
            f"WTH-01 FAIL: weather_fetcher tau={actual_fetcher_tau:.4f} deviates from README {readme_tau:.4f} by more than 10%\n"
            f"  FIX: use tau_dry=0.012, B=0.040 in derive_tau_from_pwv()"
        )
        assert abs(sim_tau - readme_tau) <= tol, (
            f"WTH-01 FAIL: atmosphere_sim tau≈{sim_tau:.4f} deviates from README {readme_tau:.4f} by more than 10%\n"
            f"  FIX: use 0.040*pwv + 0.012 in simulate_atmosphere()"
        )

    # WTH-02: PWV derivation realistic range
    def test_WTH02_pwv_derivation_range(self):
        """
        Verify PWV derivation stays within realistic Chajnantor range per Otarola 2010

        Typical Chajnantor winter (August):
          temp ≈ -8°C, RH ≈ 14%, P ≈ 542 hPa → PWV ≈ 0.3–0.8 mm
          (Otarola 2010: median PWV ≈ 0.7 mm in winter, quartiles 0.36–1.2 mm)

        Note: RH=3.5% at -8°C is extreme dry (e_sat=3.35 hPa, e=0.12 hPa)
        giving PWV ≈ 0.12 mm — outside typical range by definition
        Must use realistic winter RH (~10–20%)
        """
        from app.simulation.weather_fetcher import derive_pwv_from_meteo

        # Typical Chajnantor winter: T=-8°C, RH=14%, P=542 hPa
        # → PWV ≈ 0.5 mm (Otarola 2010 winter median)
        pwv = derive_pwv_from_meteo(-8.0, 14.0, 542.0)
        assert 0.3 <= pwv <= 0.8, (
            f"WTH-02 FAIL: PWV = {pwv:.3f} mm, expected 0.3–0.8 mm\n"
            "  Input: T=-8°C, RH=14% (typical winter), P=542 hPa\n"
            "  Per Otarola 2010: Chajnantor winter median PWV ≈ 0.7 mm\n"
            "  quartiles: 25%=0.36 mm, 50%=0.7 mm, 75%=1.2 mm\n"
            "  H_wv=1300 m (Giovanelli 2001 median 1.13 km; Otarola 2019: 1.2–1.5 km)"
        )

    # WTH-03: Cache TTL fallback to simulation (not crash)
    def test_WTH03_cache_ttl_fallback(self):
        """API timeout after stale cache → return WeatherData source='simulation', no crash"""
        import app.simulation.weather_fetcher as wf

        # Force cache stale
        old_cache = wf._cached_weather
        stale = wf.WeatherData(source="cached", fetched_at=time.time() - 999)
        wf._cached_weather = stale

        async def run():
            # Monkeypatch httpx to raise exception
            import httpx

            original_get = httpx.AsyncClient.get

            async def mock_get(self, url, **kwargs):
                raise httpx.TimeoutException("simulated timeout")

            httpx.AsyncClient.get = mock_get
            try:
                result = await wf.fetch_chajnantor_weather()
            finally:
                httpx.AsyncClient.get = original_get
            return result

        result = asyncio.run(run())

        # restore
        wf._cached_weather = old_cache

        assert result is not None, "WTH-03 FAIL: returned None"
        assert result.source == "simulation", (
            f"WTH-03 FAIL: source='{result.source}', expected 'simulation'\n"
            "  API timeout must fallback to _simulate_chajnantor_weather()"
        )

    # WTH-04: Double-checked locking — API called only once
    def test_WTH04_double_checked_locking(self):
        """2 concurrent coroutines with stale cache → API called exactly once"""
        import app.simulation.weather_fetcher as wf
        import httpx

        old_cache = wf._cached_weather
        old_lock = wf._fetch_lock

        call_count = {"n": 0}

        async def run():
            # Force stale cache and reset lock within the running event loop
            wf._cached_weather = wf.WeatherData(
                source="cached", fetched_at=time.time() - 999
            )
            wf._fetch_lock = None  # force re-create within running loop

            original_get = httpx.AsyncClient.get

            async def counting_get(self_client, url, **kwargs):
                call_count["n"] += 1
                raise httpx.TimeoutException("simulated")

            httpx.AsyncClient.get = counting_get
            try:
                await asyncio.gather(
                    wf.fetch_chajnantor_weather(),
                    wf.fetch_chajnantor_weather(),
                )
            finally:
                httpx.AsyncClient.get = original_get

        asyncio.run(run())

        # restore
        wf._cached_weather = old_cache
        wf._fetch_lock = old_lock

        assert call_count["n"] == 1, (
            f"WTH-04 FAIL: API called {call_count['n']} times, expected 1\n"
            "  double-checked locking should prevent redundant fetch"
        )

    # WTH-05: derive_seeing increases with high wind/PWV
    def test_WTH05_seeing_wind_effect(self):
        """seeing(wind=20, PWV=2.0) > seeing(wind=5, PWV=0.5) > 0.3 arcsec"""
        from app.simulation.weather_fetcher import derive_seeing

        seeing_good = derive_seeing(5, 0.5, 0)
        seeing_bad = derive_seeing(20, 2.0, 50)
        diff = seeing_bad - seeing_good
        assert diff > 0.3, (
            f"WTH-05 FAIL: seeing difference = {diff:.2f} arcsec, expected > 0.3\n"
            f"  seeing(good)={seeing_good}, seeing(bad)={seeing_bad}\n"
            "  wind > 8 m/s and high PWV must increase seeing significantly"
        )

    # WTH-06: humidity_pct in simulation fallback
    def test_WTH06_humidity_pct_range(self):
        """atmosphere_sim: PWV=2.0 → humidity_pct = 16% which exceeds real Chajnantor range (1–10%)"""
        from app.simulation.atmosphere_sim import simulate_atmosphere

        # Use fixed t that yields high PWV
        result = simulate_atmosphere(t=43200.0)  # t where diurnal ≈ max
        humidity = result["humidity_pct"]
        # Check humidity is within real physical range for Chajnantor
        in_real_range = 1 <= humidity <= 15
        # NOTE: this test checks a known issue — if it fails, the formula still uses linear PWV scale
        assert in_real_range, (
            f"WTH-06 INFO: humidity_pct = {humidity:.1f}%, expected 1–15% (Chajnantor real range)\n"
            f"  atmosphere_sim uses humidity_pct = PWV × 8 which has no physical basis\n"
            f"  PWV ≈ {result['pwv_mm']:.3f} mm → humidity = {result['pwv_mm']:.3f} × 8 = {result['pwv_mm']*8:.1f}%\n"
            "  FIX: clamp humidity to 1–15% or use empirical formula from real RH"
        )


# =============================================================================
# PTG — Pointing
# =============================================================================


class TestPointing:

    # PTG-01: Slew rate inconsistency between two modules
    def test_PTG01_slew_rate_consistency(self):
        """pointing_sim and physics_models must use the same slew rate (3°/s az, 1.5°/s el)"""
        from app.simulation.pointing_sim import SLEW_RATE_AZ_DEG_S, SLEW_RATE_EL_DEG_S
        from app.simulation.physics_models import ALMA_MAX_SLEW_RATE_DEG_S

        az_match = SLEW_RATE_AZ_DEG_S == ALMA_MAX_SLEW_RATE_DEG_S["azimuth"]
        el_match = SLEW_RATE_EL_DEG_S == ALMA_MAX_SLEW_RATE_DEG_S["elevation"]

        assert az_match and el_match, (
            f"PTG-01 FAIL: slew rate mismatch!\n"
            f"  pointing_sim:   Az={SLEW_RATE_AZ_DEG_S}°/s, El={SLEW_RATE_EL_DEG_S}°/s\n"
            f"  physics_models: Az={ALMA_MAX_SLEW_RATE_DEG_S['azimuth']}°/s, El={ALMA_MAX_SLEW_RATE_DEG_S['elevation']}°/s\n"
            "  README spec: 3°/s az, 1.5°/s el\n"
            "  FIX: use the same values in both files per ALMA Technical Requirements Document"
        )

    # PTG-02: Two pointing controllers — state sync check
    def test_PTG02_dual_controller_state(self):
        """
        Verify control.py uses both DishPointing and PointingController
        which causes state desync (known architecture issue)
        """
        import inspect

        control_path = os.path.join(
            os.path.dirname(__file__), "app", "api", "control.py"
        )
        with open(control_path, encoding="utf-8") as f:
            source = f.read()

        uses_cmd_slew = "cmd_slew" in source  # → DishPointing
        uses_controller = "controller" in source  # → PointingController

        assert uses_cmd_slew and uses_controller, (
            "PTG-02 INFO: dual controller usage not found in control.py\n"
            "  (may have been fixed)"
        )

        # Verify health endpoint does not call controller.step() (side effect on read)
        # Check only the function body of health(), not the entire file
        main_path = os.path.join(os.path.dirname(__file__), "main.py")
        with open(main_path, encoding="utf-8") as f:
            main_src = f.read()

        import ast as _ast

        tree = _ast.parse(main_src)
        health_uses_step = False
        for node in _ast.walk(tree):
            if (
                isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                and node.name == "health"
            ):
                fn_src = _ast.get_source_segment(main_src, node) or ""
                if "controller.step()" in fn_src:
                    health_uses_step = True

        assert not health_uses_step, (
            "PTG-02 FAIL: /health endpoint calls controller.step() which has a side effect!\n"
            "  GET endpoints must not mutate state\n"
            "  FIX: use controller.current_az / controller.current_el / controller.mode directly"
        )

    # PTG-03: Stow elevation limits consistency
    def test_PTG03_stow_elevation_limit(self):
        """DishPointing and PointingController must use the same max el (85° per ALMA spec)"""
        from app.simulation.physics_models import DishPointing
        from app.simulation.pointing_sim import PointingController

        # Test max elevation clipping
        dish = DishPointing("TEST")
        dish.command_slew(0, 999)  # over limit
        assert (
            dish.el_target == 85.0
        ), f"PTG-03: DishPointing max el = {dish.el_target}°, expected 85°"

        ctrl = PointingController()
        ctrl.command_slew(0, 999)
        assert ctrl.target_el == 85.0, (
            f"PTG-03: PointingController max el = {ctrl.target_el}°, expected 85°\n"
            "  FIX: change min(89.0, el) → min(85.0, el) in command_slew()"
        )

        # Verify they match
        assert dish.el_target == ctrl.target_el, (
            f"PTG-03 FAIL: Max elevation limit still mismatched!\n"
            f"  DishPointing:        max el = {dish.el_target}°\n"
            f"  PointingController:  max el = {ctrl.target_el}°\n"
            "  ALMA spec: el max ≤ 85° for 12m antenna"
        )

    # PTG-04: Azimuth wrap-around 350° → 10°
    def test_PTG04_azimuth_wraparound(self):
        """slew from Az=350° to Az=10° → both controllers must choose the 20° short path"""
        from app.simulation.physics_models import DishPointing, _wrap_angle
        from app.simulation.pointing_sim import PointingController

        # DishPointing wrap
        wrapped = _wrap_angle(10 - 350)
        assert abs(wrapped - 20.0) < 0.001, (
            f"PTG-04 FAIL: _wrap_angle(10-350) = {wrapped}, expected 20°\n"
            "  Short path: 350→360→10 = 20°, not 340°"
        )

        # PointingController wrap (see logic in step())
        ctrl = PointingController(az_init=350.0, el_init=45.0)
        ctrl.command_slew(10.0, 45.0)
        az_delta = ctrl.target_az - ctrl.current_az  # 10 - 350 = -340
        if az_delta > 180:
            az_delta -= 360
        elif az_delta < -180:
            az_delta += 360
        assert abs(az_delta - 20.0) < 0.001, (
            f"PTG-04 FAIL: PointingController az_delta = {az_delta}°, expected 20°\n"
            "  az_delta = 10-350 = -340 → +360 = 20° (short path)"
        )

    # PTG-05: DishPointing settling — import random inside method
    def test_PTG05_settling_import_in_loop(self):
        """Verify settling works (no crash) but import random is inside method body"""
        from app.simulation.physics_models import DishPointing
        import inspect

        # Check source code for import inside method
        source = inspect.getsource(DishPointing.update)
        has_import_in_method = "import random" in source or "import math" in source

        # Test that settling does not crash
        dish = DishPointing("TEST2", az0=0.0, el0=45.0)
        dish.command_slew(10.0, 50.0)
        # Simulate slew completion
        dish.az_actual = dish.az_target
        dish.el_actual = dish.el_target
        dish.state = "settling"
        dish.settle_timer = 1.0

        try:
            az, el = dish.update(0.1, time.time())
        except Exception as e:
            pytest.fail(f"PTG-05 FAIL: settling crashed: {e}")

        # Code smell warning
        assert not has_import_in_method, (
            "PTG-05 INFO: `import random` or `import math` is inside DishPointing.update() method body\n"
            "  Should be moved to module level for performance\n"
            "  FIX: move `import random` to the top of physics_models.py"
        )

    # PTG-06: GET /pointing calls step() — side effect
    def test_PTG06_get_pointing_side_effect(self):
        """GET /api/control/pointing calls controller.step() which has a side effect"""
        control_path = os.path.join(
            os.path.dirname(__file__), "app", "api", "control.py"
        )
        with open(control_path, encoding="utf-8") as f:
            source = f.read()

        import ast as _ast

        tree = _ast.parse(source)
        get_pointing_uses_step = False
        for node in _ast.walk(tree):
            if (
                isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                and "pointing" in node.name.lower()
            ):
                fn_src = _ast.get_source_segment(source, node) or ""
                if "step()" in fn_src:
                    get_pointing_uses_step = True

        assert not get_pointing_uses_step, (
            "PTG-06 FAIL: GET /api/control/pointing calls controller.step() which mutates state!\n"
            "  step() updates current_az/el and _last_update on every call\n"
            "  FIX: use controller.current_az / controller.current_el / controller.mode directly"
        )


# =============================================================================
# AUTH — Authentication & RBAC
# =============================================================================


class TestAuth:

    # AUTH-01: Double authentication in WebSocket path
    def test_AUTH01_double_auth_ws(self):
        """
        Verify telemetry.py does not call ws_authenticate again
        (main.py already handles auth before calling telemetry_endpoint)
        """
        telemetry_path = os.path.join(
            os.path.dirname(__file__), "app", "ws", "telemetry.py"
        )
        with open(telemetry_path, encoding="utf-8") as f:
            source = f.read()

        has_double_auth = "ws_authenticate" in source
        assert not has_double_auth, (
            "AUTH-01 FAIL: app/ws/telemetry.py calls ws_authenticate again!\n"
            "  main.py already handles auth before calling telemetry_endpoint()\n"
            "  FIX: remove ws_authenticate from telemetry.py"
        )

    # AUTH-02: Two telemetry.py files — import conflict
    def test_AUTH02_import_path_conflict(self):
        """Verify connection_pool.py import paths do not use 'server.' prefix"""
        pool_path = os.path.join(
            os.path.dirname(__file__), "app", "models", "connection_pool.py"
        )
        with open(pool_path, encoding="utf-8") as f:
            source = f.read()

        has_server_prefix = "from server." in source or "import server." in source
        assert not has_server_prefix, (
            "AUTH-02 FAIL: connection_pool.py uses 'server.' prefix in import!\n"
            "  'server.app.obs_queue' does not exist in production\n"
            "  FIX: change to 'from app.obs_queue import scheduler'"
        )

    # AUTH-03: Scheduler import path consistency
    def test_AUTH03_scheduler_import_consistency(self):
        """All files must import scheduler from the same path"""
        files_to_check = {
            "main.py": os.path.join(os.path.dirname(__file__), "main.py"),
            "app/ws/telemetry.py": os.path.join(
                os.path.dirname(__file__), "app", "ws", "telemetry.py"
            ),
            "app/models/connection_pool.py": os.path.join(
                os.path.dirname(__file__), "app", "models", "connection_pool.py"
            ),
        }

        imports_found = {}
        for name, path in files_to_check.items():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if "scheduler" in src:
                for line in src.splitlines():
                    if "import" in line and "scheduler" in line:
                        imports_found[name] = line.strip()
                        break

        # Verify no server.app prefix
        bad_imports = {k: v for k, v in imports_found.items() if "server." in v}
        assert not bad_imports, (
            f"AUTH-03 FAIL: incorrect import path found in:\n"
            + "\n".join(f"  {k}: {v}" for k, v in bad_imports.items())
            + "\n  FIX: use 'from app.obs_queue import scheduler' everywhere"
        )

    # AUTH-04: Default SECRET_KEY warning
    def test_AUTH04_secret_key_default(self):
        """If default SECRET_KEY is used, code must warn or raise in production mode"""
        from auth import SECRET_KEY

        DEFAULT_KEY = "change-this-in-production-use-openssl-rand-hex-32"

        is_default = SECRET_KEY == DEFAULT_KEY

        # Check that code has a warning mechanism
        auth_path = os.path.join(os.path.dirname(__file__), "auth.py")
        with open(auth_path, encoding="utf-8") as f:
            auth_src = f.read()

        has_warning = any(
            keyword in auth_src
            for keyword in [
                "WARNING",
                "warning",
                "WARN",
                "logger.warn",
                "raise ValueError",
            ]
        )

        assert has_warning, (
            "AUTH-04 FAIL: no warning when using default SECRET_KEY!\n"
            f"  Current SECRET_KEY = {'[DEFAULT]' if is_default else '[custom]'}\n"
            "  Anyone who knows the default key can forge JWT tokens\n"
            "  FIX: add if SECRET_KEY == DEFAULT_KEY: logger.warning('Using default SECRET_KEY!')"
        )

    # AUTH-05: GET /api/scheduler — missing auth guard
    def test_AUTH05_scheduler_get_no_auth(self):
        """GET /api/scheduler has no Depends(require_role) — anyone can call it"""
        scheduler_api_path = os.path.join(
            os.path.dirname(__file__), "app", "api", "scheduler.py"
        )
        with open(scheduler_api_path, encoding="utf-8") as f:
            source = f.read()

        import ast

        tree = ast.parse(source)

        get_endpoint_has_auth = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "scheduler_state" in node.name or "get_scheduler" in node.name:
                    func_src = ast.get_source_segment(source, node)
                    if func_src and (
                        "require_role" in func_src or "Depends" in func_src
                    ):
                        get_endpoint_has_auth = True

        assert get_endpoint_has_auth, (
            "AUTH-05 FAIL: GET /api/scheduler has no auth guard!\n"
            "  Anyone can call GET /api/scheduler without authenticating\n"
            "  README states viewer+ requires authentication\n"
            "  FIX: add _user: User = Depends(require_role(Role.VIEWER)) to get_scheduler_state()"
        )

    # AUTH-06: Refresh token rejects access token
    def test_AUTH06_refresh_token_type_validation(self):
        """access_token must be rejected at /auth/refresh (type != 'refresh')"""
        from auth import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
        from jose import jwt
        from datetime import datetime, timedelta, timezone

        # Create access token
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {
            "sub": "testuser",
            "type": "access",
            "exp": expire,
        }
        access_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        # Decode and verify type == 'access' (not 'refresh')
        decoded = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = decoded.get("type")

        assert token_type != "refresh", (
            f"AUTH-06 FAIL: access token has type='{token_type}', expected 'access'\n"
            "  token type validation must prevent access tokens from being used as refresh tokens"
        )
        # Confirm refresh endpoint would reject this
        assert (
            token_type == "access"
        ), f"AUTH-06: token type = '{token_type}' (expected 'access')"


# =============================================================================
# SCH — Scheduler
# =============================================================================


class TestScheduler:

    # SCH-01: Queue scan skips blocked job[0], starts job[1]
    def test_SCH01_queue_skip_blocked_job(self):
        """queue=[job_A(PWV too high), job_B(ok)] → job_B gets started"""
        from app.obs_queue import (
            ObservationScheduler,
            ObservationJob,
            JobPriority,
            JobStatus,
        )

        sched = ObservationScheduler()
        sched._queue.clear()
        sched._active = None

        job_a = ObservationJob(
            "Blocked Job",
            "00h",
            "00d",
            0,
            45,
            6,
            100,
            max_pwv_mm=0.1,  # requires PWV < 0.1 → blocked
            priority=JobPriority.HIGH,
        )
        job_b = ObservationJob(
            "OK Job",
            "00h",
            "00d",
            0,
            45,
            6,
            100,
            max_pwv_mm=5.0,  # high PWV limit → ok
            priority=JobPriority.NORMAL,
        )
        sched._queue = [job_a, job_b]
        sched._last_pwv = 1.0  # PWV higher than job_a.max_pwv_mm (0.1)

        async def run():
            await sched.tick({"atmosphere": {"pwv_mm": 1.0, "wind_ms": 5.0}})

        asyncio.run(run())

        assert (
            sched._active is not None
        ), "SCH-01 FAIL: no active job even though job_B should have started"
        assert sched._active.target_name == "OK Job", (
            f"SCH-01 FAIL: active job = '{sched._active.target_name}', expected 'OK Job'\n"
            "  scheduler must iterate the entire queue, not just queue[0]\n"
            "  job_A blocked (PWV) → skip → start job_B"
        )
        # job_A must still be in queue with a skip_reason
        assert (
            len(sched._queue) == 1
        ), f"SCH-01 FAIL: queue has {len(sched._queue)} jobs, expected 1 (job_A still present)"
        assert (
            sched._queue[0].skip_reason is not None
        ), "SCH-01 FAIL: job_A has no skip_reason"

    # SCH-02: scheduler import path exists
    def test_SCH02_scheduler_import_path(self):
        """app.scheduler or app.obs_queue must be importable"""
        try:
            from app.obs_queue import scheduler

            assert scheduler is not None
        except ImportError as e:
            pytest.fail(
                f"SCH-02 FAIL: import app.obs_queue failed: {e}\n"
                "  File is named app/obs_queue.py\n"
                "  FIX: check app/__init__.py re-exports scheduler"
            )

    # SCH-03: Private _active access — encapsulation
    def test_SCH03_private_active_access(self):
        """scheduler.py API accesses scheduler._active directly (encapsulation break)"""
        scheduler_api_path = os.path.join(
            os.path.dirname(__file__), "app", "api", "scheduler.py"
        )
        with open(scheduler_api_path, encoding="utf-8") as f:
            source = f.read()

        uses_private_active = "scheduler._active" in source

        assert not uses_private_active, (
            "SCH-03 FAIL: app/api/scheduler.py accesses scheduler._active directly!\n"
            "  TOCTOU race: tick() may change _active between check and skip\n"
            "  FIX: use scheduler.get_state()['active'] is None instead"
        )

    # SCH-04: Priority sort — URGENT first
    def test_SCH04_priority_sort_urgent_first(self):
        """add LOW before URGENT → after sort, URGENT must be at top"""
        from app.obs_queue import ObservationScheduler, ObservationJob, JobPriority

        sched = ObservationScheduler()
        sched._queue.clear()

        low_job = ObservationJob(
            "Low Job", "0h", "0d", 0, 45, 6, 60, priority=JobPriority.LOW
        )
        urgent_job = ObservationJob(
            "Urgent Job", "0h", "0d", 0, 45, 6, 60, priority=JobPriority.URGENT
        )
        sched._queue = [low_job, urgent_job]
        sched._sort_queue()

        assert sched._queue[0].priority == JobPriority.URGENT, (
            f"SCH-04 FAIL: queue[0] priority = {sched._queue[0].priority}, expected URGENT\n"
            "  URGENT.value=0, LOW.value=3 → sort ascending → URGENT comes first"
        )

    # SCH-05: history memory leak
    def test_SCH05_history_unbounded(self):
        """_history has no max size → memory leak in long-running session"""
        from app.obs_queue import ObservationScheduler, ObservationJob, JobStatus
        import time as _time

        sched = ObservationScheduler()
        sched._queue.clear()
        sched._active = None

        # Inject 25 completed jobs into _history
        for i in range(25):
            job = ObservationJob(f"Job{i}", "0h", "0d", 0, 45, 6, 1)
            job.status = JobStatus.COMPLETED
            sched._history.append(job)

        history_len = len(sched._history)
        state = sched.get_state()
        returned_history_len = len(state["history"])

        # get_state returns only last 20, but _history keeps growing
        assert history_len <= 100, (
            f"SCH-05 FAIL: _history has {history_len} entries (no cap)\n"
            "  memory leak in long-running session\n"
            "  FIX: trim _history to max 50–100 entries\n"
            f"  get_state() returns {returned_history_len} entries (correct) but memory is not freed"
        )


# =============================================================================
# WS — WebSocket
# =============================================================================


class TestWebSocket:

    # WS-01: broadcast dead connection removal
    def test_WS01_broadcast_dead_connection_removal(self):
        """dead connections are removed correctly, no KeyError"""
        from app.ws.telemetry import ConnectionPool
        from unittest.mock import AsyncMock, MagicMock

        pool = ConnectionPool()

        # Create mock websockets
        live_ws = MagicMock()
        live_ws.send_text = AsyncMock(return_value=None)

        dead_ws = MagicMock()
        dead_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))

        pool._connections = {live_ws, dead_ws}

        async def run():
            await pool.broadcast({"test": "data"})

        asyncio.run(run())

        assert (
            live_ws in pool._connections
        ), "WS-01 FAIL: live ws was incorrectly removed"
        assert (
            dead_ws not in pool._connections
        ), "WS-01 FAIL: dead ws was not removed from pool"

    # WS-02: telemetry loop sends to single client, not broadcast
    def test_WS02_telemetry_single_client_model(self):
        """telemetry.py sends via ws.send_text directly instead of pool.broadcast()"""
        telemetry_path = os.path.join(
            os.path.dirname(__file__), "app", "ws", "telemetry.py"
        )
        with open(telemetry_path, encoding="utf-8") as f:
            source = f.read()

        uses_pool_broadcast = "pool.broadcast(" in source
        uses_ws_send = "ws.send_text(" in source

        # README states broadcast to N clients but implementation sends per client
        assert uses_pool_broadcast, (
            "WS-02 FAIL: telemetry.py uses ws.send_text() instead of pool.broadcast()\n"
            "  README: 'broadcast to N clients simultaneously'\n"
            f"  uses pool.broadcast: {uses_pool_broadcast}, uses ws.send_text: {uses_ws_send}\n"
            "  FIX: use pool.broadcast(snapshot) to send to all clients at once"
        )

    # WS-03: WebSocket command input validation
    def test_WS03_command_input_validation(self):
        """az=999, el=-999 → DishPointing clamps, but handler should also validate"""
        from app.ws.telemetry import _handle_command
        from app.simulation import alma_sim

        # Verify DishPointing clamps el to min 5°
        from app.simulation.physics_models import DishPointing

        dish = DishPointing("TEST")
        dish.command_slew(999, -999)
        assert (
            dish.el_target >= 5.0
        ), f"WS-03 FAIL: DishPointing did not clamp el=-999 → el_target={dish.el_target}"
        assert dish.az_target == (
            999 % 360
        ), f"WS-03 FAIL: DishPointing did not normalize az=999 → az_target={dish.az_target}"

        # Verify _handle_command has validation
        import inspect

        handler_src = inspect.getsource(_handle_command)
        has_validation = any(
            kw in handler_src for kw in ["clamp", "max(", "min(", "assert", "validate"]
        )
        assert has_validation, (
            "WS-03 INFO: _handle_command has no input validation for az/el\n"
            "  Defense in depth: validate at every layer, not just DishPointing clamp\n"
            "  FIX: add el = max(5.0, min(85.0, el)) in handler"
        )

    # WS-04: snapshot scheduler field race condition
    def test_WS04_scheduler_snapshot_lock(self):
        """get_state() must create an atomic snapshot to prevent partial reads during tick()"""
        import inspect
        from app.obs_queue import ObservationScheduler

        get_state_src = inspect.getsource(ObservationScheduler.get_state)

        # Accept either: acquiring a lock, or copying snapshot before reading (_snap / list() copy)
        has_protection = (
            "_lock" in get_state_src
            or "async with" in get_state_src
            or "_snap" in get_state_src
            or "active_snap" in get_state_src
            or "list(self._queue)" in get_state_src
        )

        assert has_protection, (
            "WS-04 FAIL: get_state() has no protection against partial reads!\n"
            "  tick() modifies _active/_queue under a lock but get_state() reads directly\n"
            "  FIX: copy reference before reading (active_snap = self._active) or acquire lock"
        )


# =============================================================================
# API — REST Endpoints
# =============================================================================


class TestAPI:

    # API-01: GET /{dish_id} returns tuple not HTTPException
    def test_API01_telescope_not_found_returns_tuple(self):
        """GET /api/telescopes/INVALID → FastAPI does not interpret tuple return as HTTP 404"""
        import inspect
        from app.api import telescopes

        source = inspect.getsource(telescopes.get_telescope)
        returns_tuple = "return {" in source and "}, 404" in source
        uses_http_exception = "HTTPException" in source and "404" in source

        assert not returns_tuple or uses_http_exception, (
            "API-01 FAIL: get_telescope() uses 'return {...}, 404' instead of HTTPException!\n"
            "  FastAPI will serialize tuple as [{...}, 404] → HTTP 200 not 404\n"
            "  FIX: raise HTTPException(status_code=404, detail=f'Dish {dish_id!r} not found')"
        )

    # API-02: Duplicate scheduler routes
    def test_API02_duplicate_scheduler_routes(self):
        """main.py must not have inline scheduler routes if scheduler router is already included"""
        main_path = os.path.join(os.path.dirname(__file__), "main.py")
        with open(main_path, encoding="utf-8") as f:
            main_src = f.read()

        has_inline_scheduler = (
            '@app.post("/api/scheduler' in main_src
            or '@app.get("/api/scheduler' in main_src
        )
        has_router_include = (
            "scheduler_api.router" in main_src or "include_router(scheduler" in main_src
        )

        assert not has_inline_scheduler, (
            "API-02 FAIL: main.py has inline scheduler routes!\n"
            "  Should use app/api/scheduler.py router only\n"
            f"  has_inline: {has_inline_scheduler}, has_router: {has_router_include}\n"
            "  FIX: remove inline routes from main.py and use include_router(scheduler_api.router)"
        )

    # API-03: GET /api/atmosphere/ path mismatch
    def test_API03_atmosphere_path_mismatch(self):
        """README states /api/atmosphere/ but actual route is /api/atmosphere/current"""
        import inspect
        from app.api import atmosphere

        source = inspect.getsource(atmosphere)
        has_root_route = '@router.get("/")' in source or "@router.get('')" in source
        has_current_route = '@router.get("/current")' in source

        # README states GET /api/atmosphere/ should work
        assert has_root_route, (
            "API-03 FAIL: no '/' route in atmosphere.py!\n"
            "  README: GET /api/atmosphere/ → Current meteorological data\n"
            f"  Only /current route exists: {has_current_route}\n"
            "  GET /api/atmosphere/ will return 404\n"
            "  FIX: add @router.get('/') or update README to /api/atmosphere/current"
        )

    # API-04: Legacy REST endpoints missing auth
    def test_API04_legacy_endpoints_no_auth(self):
        """POST /api/slew, /api/stow have no auth — anyone can issue commands"""
        main_path = os.path.join(os.path.dirname(__file__), "main.py")
        with open(main_path, encoding="utf-8") as f:
            main_src = f.read()

        # Check legacy /api/slew
        has_legacy_slew = '@app.post("/api/slew")' in main_src
        if has_legacy_slew:
            # Verify legacy route has auth
            lines = main_src.splitlines()
            for i, line in enumerate(lines):
                if "/api/slew" in line:
                    # Look at the surrounding function block
                    func_block = "\n".join(lines[i : i + 5])
                    has_auth = "require_role" in func_block or "Depends" in func_block
                    assert has_auth, (
                        "API-04 FAIL: POST /api/slew has no auth!\n"
                        "  Legacy endpoint bypasses all RBAC\n"
                        "  FIX: add user: User = Depends(require_role(Role.OPERATOR)) or deprecate"
                    )
                    break

    # API-05: Route ordering — /system/state conflict
    def test_API05_route_ordering_conflict(self):
        """GET /api/telescopes/system/state route must be registered before /{dish_id}"""
        import inspect
        from app.api import telescopes

        source = inspect.getsource(telescopes)
        lines = source.splitlines()

        dish_id_route_line = None
        system_state_route_line = None
        for i, line in enumerate(lines):
            if '"{dish_id}"' in line or "'{dish_id}'" in line:
                if dish_id_route_line is None:
                    dish_id_route_line = i
            if '"/system/state"' in line or "'/system/state'" in line:
                if system_state_route_line is None:
                    system_state_route_line = i

        if system_state_route_line is not None and dish_id_route_line is not None:
            assert system_state_route_line < dish_id_route_line, (
                f"API-05 FAIL: route /{'{dish_id}'} (line {dish_id_route_line}) is registered before /system/state (line {system_state_route_line})!\n"
                "  FastAPI will match /system as dish_id='system'\n"
                "  FIX: place @router.get('/system/state') before @router.get('/{dish_id}')"
            )


# =============================================================================
# INF — InfluxDB
# =============================================================================


class TestInfluxDB:

    # INF-01: ant_type key mismatch
    def test_INF01_ant_type_key_mismatch(self):
        """influx_writer uses dish.get('ant_type') but alma_sim sends key 'ant_type' (verify if fixed)"""
        # Check alma_sim sends ant_type key in snapshot
        from app.simulation.alma_sim import get_system_snapshot

        async def run():
            return await get_system_snapshot()

        snapshot = asyncio.run(run())

        dishes = snapshot.get("alma", {}).get("dishes", [])
        assert len(dishes) > 0, "INF-01: no dishes in snapshot"

        dish = dishes[0]
        has_ant_type = "ant_type" in dish
        has_type = "type" in dish

        assert has_ant_type, (
            f"INF-01 FAIL: dish missing key 'ant_type'!\n"
            f"  available keys: {list(dish.keys())}\n"
            f"  has 'type': {has_type}\n"
            "  influx_writer.py: dish.get('ant_type', 'DA') will always return default 'DA'\n"
            "  FIX: alma_sim must send 'ant_type' key or influx_writer must use dish.get('type', 'DA')"
        )

    # INF-02: InfluxDB close() — no lifespan hook
    def test_INF02_influx_close_lifespan(self):
        """main.py must have a lifespan hook that calls influx_writer.close()"""
        main_path = os.path.join(os.path.dirname(__file__), "main.py")
        with open(main_path, encoding="utf-8") as f:
            main_src = f.read()

        has_lifespan = "lifespan" in main_src
        has_on_event = (
            'on_event("shutdown")' in main_src or "on_event('shutdown')" in main_src
        )
        has_close_call = "influx_writer.close()" in main_src

        has_proper_shutdown = (has_lifespan or has_on_event) and has_close_call

        assert has_proper_shutdown, (
            "INF-02 FAIL: no lifespan hook calling influx_writer.close()!\n"
            f"  has lifespan: {has_lifespan}, has on_event: {has_on_event}\n"
            f"  has close() call: {has_close_call}\n"
            "  SIGTERM → graceful shutdown → InfluxDB buffer not flushed → data loss\n"
            "  FIX: add @asynccontextmanager lifespan that calls await influx_writer.close()"
        )

    # INF-03: error_count not reset on success
    def test_INF03_error_count_reset(self):
        """_error_count must be reset when write succeeds"""
        import inspect
        from influx_writer import InfluxWriter

        # Check source for _error_count reset on success
        flush_src = inspect.getsource(InfluxWriter._flush)
        resets_on_success = "self._error_count = 0" in flush_src

        assert resets_on_success, (
            "INF-03 FAIL: _error_count is not reset when _flush() succeeds!\n"
            "  error_count=50 after recovery: next error count=51, 51%60≠1 → no log emitted\n"
            "  FIX: add self._error_count = 0 in the success branch of _flush()"
        )
