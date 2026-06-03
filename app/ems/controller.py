"""
EMSController – orchestrates the full control cycle.

Devices are created ONCE at startup and persist across cycles so that internal
state (e.g. BinaryDevice._off_since_ts) survives between invocations without
needing HA helper entities.
"""

import datetime
import logging
from typing import Dict, List, Optional

from .state import StateProxy, safe_float
from .devices import Device, ControllableDevice, BinaryDevice

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global HA entity names
# ---------------------------------------------------------------------------

HA_EMS_ENABLED               = "input_boolean.ems_pv_regelung_aktiv"
HA_GLOBAL_MODE               = "input_select.ems_regelmodus"
HA_RESIDUAL_W                = "sensor.verfugbare_leistung_fur_uberschusverbraucher"
HA_GLOBAL_PUFFER_W           = "input_number.ems_globaler_puffer_w"
HA_GLOBAL_EINSCHALTRESERVE_W = "input_number.ems_einschaltreserve_global_w"
HA_DEBUG_OUTPUT              = "input_boolean.ems_pyems_debug_output"

HARD_LOCKOUT_THRESHOLD_W = -50000.0


# ---------------------------------------------------------------------------
# Device registry – built from add-on config at startup
# ---------------------------------------------------------------------------

def _build_devices(device_configs: List[dict]) -> List[Device]:
    """Build device list from config.yaml options.devices entries."""
    devices = []
    for cfg in device_configs:
        name = (cfg.get("name") or "").strip()
        cls  = (cfg.get("class") or "").strip()
        if not name:
            log.error("Gerätekonfiguration ohne 'name' übersprungen: %s", cfg)
            continue

        prefix = (cfg.get("entity_prefix") or "").strip() or name
        label  = (cfg.get("label")         or "").strip() or None
        modes  = [m.strip() for m in (cfg.get("allowed_modes") or "auto").split(",") if m.strip()]

        try:
            if cls == "controllable":
                actual_w = (cfg.get("actual_power_entity") or "").strip()
                if not actual_w:
                    raise ValueError("actual_power_entity ist leer")
                output_unit          = (cfg.get("output_unit") or "watt").strip()
                phases_raw           = (cfg.get("phases") or "1").strip()
                allowed_phases       = [int(p) for p in phases_raw.split(",")
                                        if p.strip() in ("1", "3")]
                if not allowed_phases:
                    allowed_phases = [1]
                phase_switch_delay_s = float(cfg.get("phase_switch_delay_s") or 300)
                def _ve(key: str) -> Optional[str]:
                    return (cfg.get(key) or "").strip() or None
                anf_suf              = 'a' if output_unit == 'ampere' else 'w'
                devices.append(ControllableDevice(
                    id=name,
                    allowed_modes=modes,
                    entity_actual_w=actual_w,
                    entity_anforderung_w=f"input_number.ems_{prefix}_anforderung_leistung_{anf_suf}",
                    entity_prefix=prefix,
                    label=label,
                    output_unit=output_unit,
                    allowed_phases=allowed_phases,
                    voltage_l1_entity=_ve("voltage_l1_entity"),
                    voltage_l2_entity=_ve("voltage_l2_entity"),
                    voltage_l3_entity=_ve("voltage_l3_entity"),
                    phase_switch_delay_s=phase_switch_delay_s,
                ))

            elif cls == "binary":
                switch = (cfg.get("switch_entity") or "").strip()
                if not switch:
                    raise ValueError("switch_entity ist leer")
                devices.append(BinaryDevice(
                    id=name,
                    allowed_modes=modes,
                    entity_switch=switch,
                    entity_anforderung_an=f"input_boolean.ems_{prefix}_anforderung_an",
                    entity_prefix=prefix,
                    label=label,
                ))

            else:
                raise ValueError(f"Unbekannte Klasse '{cls}' (erlaubt: controllable, binary)")

            log.info("Gerät registriert: '%s' (%s, prefix='%s', modi=%s)",
                     name, cls, prefix, modes)

        except Exception as exc:
            log.error("Gerät '%s' konnte nicht registriert werden: %s", name, exc)

    return devices


# ---------------------------------------------------------------------------
# EMSController
# ---------------------------------------------------------------------------

class EMSController:
    """
    Stateful EMS controller.  Instantiated once in HEMSApp; device objects
    and their internal state persist across all cycles.
    """

    def __init__(self, device_configs: List[dict]):
        self._devices: List[Device] = _build_devices(device_configs)
        log.info("EMSController ready – %d devices registered.", len(self._devices))

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_cycle(self, st: StateProxy) -> Dict:
        """
        Execute one control cycle.

        Returns:
            {
                "status":    { ... },              # web-UI snapshot
                "write_ops": [(domain, svc, data)] # HA service calls to execute
            }
        """
        now_ts = datetime.datetime.now().timestamp()
        now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── 1. Global inputs ────────────────────────────────────────────
        debug_output            = st.get(HA_DEBUG_OUTPUT) == "on"
        ems_enabled             = st.get(HA_EMS_ENABLED) == "on"
        global_mode             = st.get(HA_GLOBAL_MODE) or "aus"
        global_puffer           = safe_float(st.get(HA_GLOBAL_PUFFER_W))
        global_einschaltreserve = safe_float(st.get(HA_GLOBAL_EINSCHALTRESERVE_W))

        residual_raw          = st.get(HA_RESIDUAL_W)
        residual_sensor_valid = residual_raw not in ("unavailable", "unknown", None)
        residual_w            = safe_float(residual_raw) if residual_sensor_valid else 0.0
        hard_lockout          = (not residual_sensor_valid
                                 or residual_w <= HARD_LOCKOUT_THRESHOLD_W)

        if not residual_sensor_valid:
            log.error("EMS SENSOR LOCKOUT: %s ist '%s' – alle Verbraucher abschalten",
                      HA_RESIDUAL_W, residual_raw)
        elif hard_lockout and debug_output:
            log.warning("EMS LOCKOUT: residual=%.0fW <= %.0fW",
                        residual_w, HARD_LOCKOUT_THRESHOLD_W)

        # ── 2. Update all devices from HA ───────────────────────────────
        for device in self._devices:
            device.eligible = device.check_eligible(
                st, ems_enabled, global_mode, hard_lockout
            )
            device.update_from_ha(st, now_ts, global_puffer)

        # ── 3. Pool ─────────────────────────────────────────────────────
        pool_w = self._calc_pool(residual_w, ems_enabled, global_mode, hard_lockout)

        # ── 4. Phase selection (multi-phase controllable devices) ────────
        for device in self._devices:
            if isinstance(device, ControllableDevice) and device.eligible:
                device.select_phases(pool_w, now_ts)

        # ── 5. Deficit ──────────────────────────────────────────────────
        current_deficit_w    = max(-residual_w, 0.0)
        controllable_relief  = sum(d.max_relief_w for d in self._devices)
        binary_immediate_off = current_deficit_w > controllable_relief

        if current_deficit_w > 0 and debug_output:
            log.warning("EMS DEFIZIT: %.0fW  sofort_aus=%s",
                        current_deficit_w, binary_immediate_off)

        # ── 6. Binary desired state (pool consumed in priority order) ───
        remaining_w = pool_w
        for device in sorted(self._devices, key=lambda d: d.priority):
            remaining_w = device.consume_from_pool(remaining_w, global_einschaltreserve)

        # ── 7. Binary candidate (timing guards, off_delay) ──────────────
        binary_devices = [d for d in self._devices if isinstance(d, BinaryDevice)]
        for device in binary_devices:
            device.calculate_candidate(now_ts, binary_immediate_off)

        # ── 8. Copy candidate → final, then apply cascade + one-change ──
        for device in binary_devices:
            device.final_on = device.candidate_on

        self._apply_priority_cascade(binary_devices)
        self._limit_one_change(binary_devices, binary_immediate_off)

        # Reset off_delay timer for devices finalised as OFF
        for device in binary_devices:
            if not device.final_on:
                device.reset_off_timer()

        # ── 9. Allocate controllable devices ────────────────────────────
        binary_total_w = sum(d.power_w for d in binary_devices if d.final_on)
        remaining_w    = max(pool_w - binary_total_w, 0.0)
        for device in sorted(self._devices, key=lambda d: d.priority):
            remaining_w = device.allocate(remaining_w)

        # ── 10. Ramp-rate limiting ───────────────────────────────────────
        for device in self._devices:
            device.calculate_ramp(current_deficit_w)

        # ── 11. Debug logging ────────────────────────────────────────────
        if debug_output:
            self._log_cycle(binary_devices, pool_w, binary_immediate_off)

        # ── 12. Collect HA write operations ─────────────────────────────
        write_ops = [op for d in self._devices for op in d.get_write_ops()]

        # ── 13. Build status snapshot for web UI ────────────────────────
        status = {
            "ems_enabled":           ems_enabled,
            "global_mode":           global_mode,
            "hard_lockout":          hard_lockout,
            "residual_sensor_valid": residual_sensor_valid,
            "residual_w":            residual_w,
            "pool_w":                pool_w,
            "current_deficit_w":     current_deficit_w,
            "binary_immediate_off":  binary_immediate_off,
            "binary_total_w":        binary_total_w,
            "devices":               [d.to_status_dict() for d in self._devices],
            "timestamp":             now_dt,
        }

        return {"status": status, "write_ops": write_ops}

    # ------------------------------------------------------------------
    # Pool
    # ------------------------------------------------------------------

    def _calc_pool(self, residual_w: float, ems_enabled: bool,
                   global_mode: str, hard_lockout: bool) -> float:
        if not ems_enabled or global_mode == "aus" or hard_lockout:
            return 0.0
        actual_used_w = sum(d.current_w for d in self._devices)
        return max(residual_w + actual_used_w, 0.0)

    # ------------------------------------------------------------------
    # Priority cascade
    # ------------------------------------------------------------------

    def _apply_priority_cascade(self, binary_devices: List[BinaryDevice]) -> None:
        sorted_b = sorted(binary_devices, key=lambda d: d.priority)

        # Demotion: lower-priority device must go off first
        for i, high in enumerate(sorted_b):
            if not high.desired_on and high.final_on:
                for low in sorted_b[i + 1:]:
                    if not low.desired_on and low.final_on and not low.in_min_runtime:
                        low.final_on = False

        # Promotion: higher-priority must not be off while lower-priority is on
        for i, high in enumerate(sorted_b):
            for low in sorted_b[i + 1:]:
                if low.final_on:
                    if high.eligible and (high.actual_on or high.candidate_on):
                        high.final_on = True
                        high.reset_off_timer()

    # ------------------------------------------------------------------
    # One-change limit
    # ------------------------------------------------------------------

    def _limit_one_change(self, binary_devices: List[BinaryDevice],
                          binary_immediate_off: bool) -> None:
        if binary_immediate_off:
            return

        turn_offs = [d for d in binary_devices if d.actual_on  and not d.final_on]
        turn_ons  = [d for d in binary_devices if not d.actual_on and d.final_on]

        if len(turn_offs) + len(turn_ons) <= 1:
            return

        if turn_offs:
            # Least important (highest priority number) turns off first
            for d in sorted(turn_offs, key=lambda d: d.priority, reverse=True)[1:]:
                d.final_on = True
            for d in turn_ons:
                d.final_on = False
        else:
            # Only turn-ons: highest priority (lowest number) wins
            for d in sorted(turn_ons, key=lambda d: d.priority)[1:]:
                d.final_on = False

    # ------------------------------------------------------------------
    # Debug logging
    # ------------------------------------------------------------------

    def _log_cycle(self, binary_devices: List[BinaryDevice],
                   pool_w: float, binary_immediate_off: bool) -> None:
        for d in binary_devices:
            if d.actual_on != d.final_on:
                direction = "AUS→AN" if d.final_on else "AN→AUS"
                reason    = ("Notabschaltung" if binary_immediate_off and not d.final_on
                             else "desired" + ("=JA" if d.final_on else "=NEIN"))
                log.info("EMS [%s] %s  prio=%d  pool=%.0fW  %s",
                         d.id, direction, d.priority, pool_w, reason)
            elif d.actual_on and d.final_on and not d.desired_on:
                if d.in_min_runtime:
                    log.info("EMS [%s] BLEIBT AN  min_runtime schützt", d.id)
                elif d.candidate_on and d._off_since_ts > 0:
                    elapsed = datetime.datetime.now().timestamp() - d._off_since_ts
                    log.info("EMS [%s] BLEIBT AN  off_delay läuft (%.0fs)", d.id, elapsed)

        for d in self._devices:
            if isinstance(d, ControllableDevice):
                if int(d.new_w) != int(d.anforderung_current_w):
                    log.info("EMS [%s] %.0fW→%.0fW  prio=%d  alloc=%.0fW  pool=%.0fW",
                             d.id, d.anforderung_current_w, d.new_w,
                             d.priority, d.alloc_w, pool_w)
