"""
EMS core logic – pure Python, no Home Assistant dependencies.
Ported 1:1 from pyems-2.py; HA I/O is handled by main.py / ha_client.py.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# KONFIGURATION  (same as pyems-2.py section 1)
# ---------------------------------------------------------------------------

HA_EMS_ENABLED               = "input_boolean.ems_pv_regelung_aktiv"
HA_GLOBAL_MODE               = "input_select.ems_regelmodus"
HA_RESIDUAL_W                = "sensor.verfugbare_leistung_fur_uberschusverbraucher"
HA_GLOBAL_PUFFER_W           = "input_number.ems_globaler_puffer_w"
HA_GLOBAL_EINSCHALTRESERVE_W = "input_number.ems_einschaltreserve_global_w"
HA_DEBUG_OUTPUT              = "input_boolean.ems_pyems_debug_output"

HARD_LOCKOUT_THRESHOLD_W = -50000.0
RESET_DT = "1970-01-01 00:00:00"

ELIGIBLE_MODES: Dict[str, List[str]] = {
    "heizstab":     ["auto", "nur_heizen"],
    "heizlufter_1": ["auto", "nur_heizen"],
    "heizlufter_2": ["auto", "nur_heizen"],
    "heizlufter_3": ["auto", "nur_heizen"],
    "heizlufter_4": ["auto", "nur_heizen"],
    "wallbox_1":    ["auto", "nur_laden"],
    "wallbox_2":    ["auto", "nur_laden"],
}

ELIGIBLE_ENTITIES: Dict[str, Dict[str, str]] = {
    "heizstab": {
        "freigabe": "input_boolean.ems_heizstab_freigabe",
        "modus":    "input_select.ems_heizstab_modus",
    },
    "heizlufter_1": {
        "freigabe": "input_boolean.ems_heizlufter_1_freigabe",
        "modus":    "input_select.ems_heizlufter_1_modus",
    },
    "heizlufter_2": {
        "freigabe": "input_boolean.ems_heizlufter_2_freigabe",
        "modus":    "input_select.ems_heizlufter_2_modus",
    },
    "heizlufter_3": {
        "freigabe": "input_boolean.ems_heizlufter_3_freigabe",
        "modus":    "input_select.ems_heizlufter_3_modus",
    },
    "heizlufter_4": {
        "freigabe": "input_boolean.ems_heizlufter_4_freigabe",
        "modus":    "input_select.ems_heizlufter_4_modus",
    },
    "wallbox_1": {
        "freigabe": "input_boolean.ems_wallbox_freigabe",
        "modus":    "input_select.ems_wallbox_modus",
    },
    "wallbox_2": {
        "freigabe": "input_boolean.ems_wallbox_2_freigabe",
        "modus":    "input_select.ems_wallbox_2_modus",
    },
}


# ---------------------------------------------------------------------------
# STATE PROXY  – wraps the dict fetched from HA, mimics pyscript's `state`
# ---------------------------------------------------------------------------

class StateProxy:
    def __init__(self, states: Dict[str, Dict]):
        self._states = states

    def get(self, entity_id: str, default: Any = None) -> Any:
        if entity_id.endswith(".last_changed"):
            base = entity_id[: -len(".last_changed")]
            return (self._states.get(base) or {}).get("last_changed", default)
        entry = self._states.get(entity_id)
        if entry is None:
            return default
        return entry.get("state", default)

    def getattr(self, entity_id: str) -> Optional[Dict]:
        entry = self._states.get(entity_id)
        if entry is None:
            return None
        return entry.get("attributes")


# ---------------------------------------------------------------------------
# GERÄTEKLASSEN  (section 2)
# ---------------------------------------------------------------------------

class EmsControllableDevice:
    def __init__(self, id, priority,
                 min_technisch_w, max_technisch_w,
                 geschuetzte_mindestleistung_w, reserve_w,
                 hoch_regelzeit_s, runter_regelzeit_s, max_anderung_pro_schritt_w,
                 entity_actual_w, entity_anforderung_w,
                 deadband_w=0.0):
        self.id = id
        self.priority = priority
        self.min_technisch_w = min_technisch_w
        self.max_technisch_w = max_technisch_w
        self.geschuetzte_mindestleistung_w = geschuetzte_mindestleistung_w
        self.reserve_w = reserve_w
        self.hoch_regelzeit_s = hoch_regelzeit_s
        self.runter_regelzeit_s = runter_regelzeit_s
        self.max_anderung_pro_schritt_w = max_anderung_pro_schritt_w
        self.entity_actual_w = entity_actual_w
        self.entity_anforderung_w = entity_anforderung_w
        self.deadband_w = deadband_w
        self.actual_w = 0.0
        self.anforderung_current_w = 0.0
        self.anforderung_age_s = 0.0
        self.schutz_w = 0.0
        self.alloc_w = 0.0
        self.new_w = 0.0
        self.eligible = False

    def calc_schutz_w(self, global_puffer_w):
        raw = self.geschuetzte_mindestleistung_w + self.reserve_w + global_puffer_w
        return min(raw, self.max_technisch_w)


class EmsBinaryDevice:
    def __init__(self, id, priority,
                 power_w, on_reserve_w,
                 min_runtime_s, min_offtime_s, off_delay_s,
                 entity_switch, entity_anforderung_an, entity_off_since):
        self.id = id
        self.priority = priority
        self.power_w = power_w
        self.on_reserve_w = on_reserve_w
        self.min_runtime_s = min_runtime_s
        self.min_offtime_s = min_offtime_s
        self.off_delay_s = off_delay_s
        self.entity_switch = entity_switch
        self.entity_anforderung_an = entity_anforderung_an
        self.entity_off_since = entity_off_since
        self.actual_on = False
        self.switch_age_s = 0.0
        self.off_since_ts = 0.0
        self.desired_on = False
        self.candidate_on = False
        self.final_on = False
        self.off_since_next = RESET_DT
        self.eligible = False


# ---------------------------------------------------------------------------
# GERÄTEBAU  (section 1, build_devices)
# ---------------------------------------------------------------------------

def build_devices(st: StateProxy) -> list:
    def n(entity_id, default=0.0):
        val = st.get(entity_id)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    return [
        # --- Regelbare Verbraucher ---
        EmsControllableDevice(
            id="heizstab",
            priority=int(n("input_number.ems_heizstab_prioritat", 1)),
            min_technisch_w=n("input_number.ems_heizstab_min_technisch_w"),
            max_technisch_w=n("input_number.ems_heizstab_max_technisch_w"),
            geschuetzte_mindestleistung_w=n("input_number.ems_heizstab_geschutzte_mindestleistung_w"),
            reserve_w=n("input_number.ems_heizstab_reserve_w"),
            hoch_regelzeit_s=n("input_number.ems_heizstab_hoch_regelzeit_s"),
            runter_regelzeit_s=n("input_number.ems_heizstab_runter_regelzeit_s"),
            max_anderung_pro_schritt_w=n("input_number.ems_heizstab_max_anderung_pro_schritt_w"),
            entity_actual_w="sensor.elwa_modbus_istleistung",
            entity_anforderung_w="input_number.ems_heizstab_anforderung_leistung_w",
            deadband_w=n("input_number.ems_heizstab_min_anderung_pro_schritt_w"),
        ),

        EmsControllableDevice(
            id="wallbox_1",
            priority=int(n("input_number.ems_wallbox_prioritat", 5)),
            min_technisch_w=n("input_number.ems_wallbox_min_technisch_w"),
            max_technisch_w=n("input_number.ems_wallbox_max_technisch_w"),
            geschuetzte_mindestleistung_w=n("input_number.ems_wallbox_geschutzte_mindestleistung_w"),
            reserve_w=n("input_number.ems_wallbox_reserve_w"),
            hoch_regelzeit_s=n("input_number.ems_wallbox_hoch_regelzeit_s"),
            runter_regelzeit_s=n("input_number.ems_wallbox_runter_regelzeit_s"),
            max_anderung_pro_schritt_w=n("input_number.ems_wallbox_max_anderung_pro_schritt_w"),
            entity_actual_w="sensor.wallbox_1_istleistung",
            entity_anforderung_w="input_number.ems_wallbox_anforderung_leistung_w",
        ),

        # Zweite Wallbox – auskommentieren + HA-Helfer anlegen zum Aktivieren:
        # EmsControllableDevice(
        #     id="wallbox_2",
        #     priority=int(n("input_number.ems_wallbox_2_prioritat", 6)),
        #     min_technisch_w=n("input_number.ems_wallbox_2_min_technisch_w"),
        #     max_technisch_w=n("input_number.ems_wallbox_2_max_technisch_w"),
        #     geschuetzte_mindestleistung_w=n("input_number.ems_wallbox_2_geschutzte_mindestleistung_w"),
        #     reserve_w=n("input_number.ems_wallbox_2_reserve_w"),
        #     hoch_regelzeit_s=n("input_number.ems_wallbox_2_hoch_regelzeit_s"),
        #     runter_regelzeit_s=n("input_number.ems_wallbox_2_runter_regelzeit_s"),
        #     max_anderung_pro_schritt_w=n("input_number.ems_wallbox_2_max_anderung_pro_schritt_w"),
        #     entity_actual_w="sensor.wallbox_2_istleistung",
        #     entity_anforderung_w="input_number.ems_wallbox_2_anforderung_leistung_w",
        # ),

        # --- Binäre Verbraucher ---
        EmsBinaryDevice(
            id="heizlufter_1",
            priority=int(n("input_number.ems_heizlufter_1_prioritat", 2)),
            power_w=n("input_number.ems_heizlufter_1_leistung_w"),
            on_reserve_w=n("input_number.ems_heizlufter_1_einschaltreserve_w"),
            min_runtime_s=n("input_number.ems_heizlufter_1_mindestlaufzeit_s"),
            min_offtime_s=n("input_number.ems_heizlufter_1_mindestauszeit_s"),
            off_delay_s=n("input_number.ems_heizlufter_1_abschaltverzogerung_s"),
            entity_switch="switch.heizlufter",
            entity_anforderung_an="input_boolean.ems_heizlufter_1_anforderung_an",
            entity_off_since="input_datetime.ems_heizlufter_1_abschaltanforderung_seit",
        ),

        EmsBinaryDevice(
            id="heizlufter_2",
            priority=int(n("input_number.ems_heizlufter_2_prioritat", 3)),
            power_w=n("input_number.ems_heizlufter_2_leistung_w"),
            on_reserve_w=n("input_number.ems_heizlufter_2_einschaltreserve_w"),
            min_runtime_s=n("input_number.ems_heizlufter_2_mindestlaufzeit_s"),
            min_offtime_s=n("input_number.ems_heizlufter_2_mindestauszeit_s"),
            off_delay_s=n("input_number.ems_heizlufter_2_abschaltverzogerung_s"),
            entity_switch="switch.heizlufter2",
            entity_anforderung_an="input_boolean.ems_heizlufter_2_anforderung_an",
            entity_off_since="input_datetime.ems_heizlufter_2_abschaltanforderung_seit",
        ),

        # Heizlüfter 3 – auskommentieren + HA-Helfer anlegen zum Aktivieren:
        # EmsBinaryDevice(
        #     id="heizlufter_3",
        #     priority=int(n("input_number.ems_heizlufter_3_prioritat", 4)),
        #     power_w=n("input_number.ems_heizlufter_3_leistung_w"),
        #     on_reserve_w=n("input_number.ems_heizlufter_3_einschaltreserve_w"),
        #     min_runtime_s=n("input_number.ems_heizlufter_3_mindestlaufzeit_s"),
        #     min_offtime_s=n("input_number.ems_heizlufter_3_mindestauszeit_s"),
        #     off_delay_s=n("input_number.ems_heizlufter_3_abschaltverzogerung_s"),
        #     entity_switch="switch.heizlufter3",
        #     entity_anforderung_an="input_boolean.ems_heizlufter_3_anforderung_an",
        #     entity_off_since="input_datetime.ems_heizlufter_3_abschaltanforderung_seit",
        # ),

        # Heizlüfter 4 – auskommentieren + HA-Helfer anlegen zum Aktivieren:
        # EmsBinaryDevice(
        #     id="heizlufter_4",
        #     priority=int(n("input_number.ems_heizlufter_4_prioritat", 5)),
        #     power_w=n("input_number.ems_heizlufter_4_leistung_w"),
        #     on_reserve_w=n("input_number.ems_heizlufter_4_einschaltreserve_w"),
        #     min_runtime_s=n("input_number.ems_heizlufter_4_mindestlaufzeit_s"),
        #     min_offtime_s=n("input_number.ems_heizlufter_4_mindestauszeit_s"),
        #     off_delay_s=n("input_number.ems_heizlufter_4_abschaltverzogerung_s"),
        #     entity_switch="switch.heizlufter4",
        #     entity_anforderung_an="input_boolean.ems_heizlufter_4_anforderung_an",
        #     entity_off_since="input_datetime.ems_heizlufter_4_abschaltanforderung_seit",
        # ),
    ]


# ---------------------------------------------------------------------------
# BERECHNUNGSLOGIK  (section 3 – unchanged from pyems-2.py)
# ---------------------------------------------------------------------------

def ems_calc_pool(residual_w, devices, ems_enabled, global_mode, hard_lockout):
    if not ems_enabled or global_mode == "aus" or hard_lockout:
        return 0.0
    actual_used_w = 0.0
    for d in devices:
        if isinstance(d, EmsControllableDevice):
            actual_used_w += d.actual_w
        elif isinstance(d, EmsBinaryDevice):
            actual_used_w += d.power_w if d.actual_on else 0.0
    return max(residual_w + actual_used_w, 0.0)


def ems_calc_deficit_info(residual_w, devices):
    current_deficit_w = max(-residual_w, 0.0)
    controllable_relief_w = sum(
        max(d.actual_w - d.min_technisch_w, 0.0)
        for d in devices
        if isinstance(d, EmsControllableDevice) and d.eligible
    )
    return current_deficit_w, current_deficit_w > controllable_relief_w


def ems_calc_binary_desired(devices, pool_w, global_einschaltreserve_w):
    sorted_devices = sorted(devices, key=lambda d: d.priority)
    remaining_w = pool_w
    for device in sorted_devices:
        if not device.eligible:
            continue
        if isinstance(device, EmsControllableDevice):
            remaining_w -= device.schutz_w
        elif isinstance(device, EmsBinaryDevice):
            on_threshold = device.power_w + device.on_reserve_w + global_einschaltreserve_w
            if device.actual_on:
                device.desired_on = remaining_w >= device.power_w
            else:
                device.desired_on = remaining_w >= on_threshold
            if device.desired_on:
                remaining_w -= device.power_w


def ems_calc_binary_candidate(device, now_ts, now_dt, binary_immediate_off):
    if not device.eligible:
        device.candidate_on = False
        device.off_since_next = RESET_DT
        return

    if device.actual_on:
        if device.desired_on:
            device.candidate_on = True
            device.off_since_next = RESET_DT
            return

        if binary_immediate_off:
            device.candidate_on = False
            return

        if device.switch_age_s < device.min_runtime_s:
            device.candidate_on = True
            device.off_since_next = RESET_DT
            return

        if device.off_since_ts <= 0:
            pending_elapsed = 0.0
            device.off_since_next = now_dt
        else:
            pending_elapsed = now_ts - device.off_since_ts
            device.off_since_next = _ts_to_dt(device.off_since_ts)

        if device.off_delay_s == 0 or pending_elapsed >= device.off_delay_s:
            device.candidate_on = False
        else:
            device.candidate_on = True
    else:
        device.off_since_next = RESET_DT
        device.candidate_on = device.desired_on and device.switch_age_s >= device.min_offtime_s


def ems_apply_priority_cascade(binary_devices):
    sorted_binary = sorted(binary_devices, key=lambda d: d.priority)

    # Schritt 1 – Demotion
    for i, high_prio in enumerate(sorted_binary):
        if not high_prio.desired_on and high_prio.final_on:
            for low_prio in sorted_binary[i + 1:]:
                in_min_runtime = (low_prio.actual_on
                                  and low_prio.switch_age_s < low_prio.min_runtime_s)
                if not low_prio.desired_on and low_prio.final_on and not in_min_runtime:
                    low_prio.final_on = False

    # Schritt 2 – Promotion
    for i, high_prio in enumerate(sorted_binary):
        for low_prio in sorted_binary[i + 1:]:
            if low_prio.final_on:
                if high_prio.eligible and (high_prio.actual_on or high_prio.candidate_on):
                    high_prio.final_on = True
                    high_prio.off_since_next = RESET_DT


def ems_limit_one_change(binary_devices, binary_immediate_off):
    if binary_immediate_off:
        return

    turn_offs = [d for d in binary_devices if d.actual_on and not d.final_on]
    turn_ons  = [d for d in binary_devices if not d.actual_on and d.final_on]

    if len(turn_offs) + len(turn_ons) <= 1:
        return

    if turn_offs:
        turn_offs_sorted = sorted(turn_offs, key=lambda d: d.priority, reverse=True)
        for d in turn_offs_sorted[1:]:
            d.final_on = True
        for d in turn_ons:
            d.final_on = False
    else:
        turn_ons_sorted = sorted(turn_ons, key=lambda d: d.priority)
        for d in turn_ons_sorted[1:]:
            d.final_on = False


def ems_allocate_controllable(controllable_devices, pool_w, binary_total_w):
    sorted_c = sorted(controllable_devices, key=lambda d: d.priority)
    remaining_w = max(pool_w - binary_total_w, 0.0)
    for device in sorted_c:
        if not device.eligible or remaining_w <= 0:
            device.alloc_w = 0.0
            continue
        if device.min_technisch_w == 0:
            device.alloc_w = min(remaining_w, device.max_technisch_w)
        elif remaining_w >= device.min_technisch_w:
            device.alloc_w = min(remaining_w, device.max_technisch_w)
        else:
            device.alloc_w = 0.0
        remaining_w -= device.alloc_w


def ems_calc_ramp(device, current_deficit_w=0.0):
    if not device.eligible:
        device.new_w = 0.0
        return
    ideal_w   = device.alloc_w
    current_w = device.anforderung_current_w
    age_s     = device.anforderung_age_s

    if ideal_w > current_w:
        new_w = (
            min(ideal_w, current_w + device.max_anderung_pro_schritt_w, device.max_technisch_w)
            if age_s >= device.hoch_regelzeit_s
            else current_w
        )
    elif ideal_w < current_w:
        if current_deficit_w > 0:
            new_w = ideal_w
        else:
            new_w = (
                max(ideal_w, current_w - device.max_anderung_pro_schritt_w)
                if age_s >= device.runter_regelzeit_s
                else current_w
            )
    else:
        new_w = current_w

    if 0 < new_w < device.min_technisch_w:
        new_w = device.min_technisch_w if ideal_w >= device.min_technisch_w else 0.0

    device.new_w = round(max(min(new_w, device.max_technisch_w), 0.0))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ts_to_dt(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_ts(last_changed) -> float:
    if last_changed is None:
        return 0.0
    try:
        if isinstance(last_changed, (int, float)):
            return float(last_changed)
        dt = datetime.datetime.fromisoformat(str(last_changed).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


def _check_eligible(device, st: StateProxy, ems_enabled, global_mode, hard_lockout) -> bool:
    if not ems_enabled or hard_lockout or global_mode == "aus":
        return False
    allowed_modes = ELIGIBLE_MODES.get(device.id, [])
    if global_mode not in allowed_modes:
        return False
    entities = ELIGIBLE_ENTITIES.get(device.id)
    if not entities:
        return True
    freigabe = st.get(entities.get("freigabe", "")) == "on"
    modus    = st.get(entities.get("modus", "")) == "auto"
    return freigabe and modus


def _binary_change_reason(device, binary_immediate_off) -> str:
    if not device.eligible:
        return "nicht freigegeben"
    if device.final_on and not device.actual_on:
        return (f"desired=JA  min_offtime OK "
                f"({device.switch_age_s:.0f}s/{device.min_offtime_s:.0f}s)")
    if not device.final_on and device.actual_on:
        if binary_immediate_off:
            return "Notabschaltung (Defizit > regelbare Entlastung)"
        return "desired=NEIN  off_delay abgelaufen/0"
    return ""


def _binary_protection_reason(device) -> Optional[str]:
    if not device.eligible or not device.actual_on or not device.final_on:
        return None
    if device.desired_on:
        return None
    if device.switch_age_s < device.min_runtime_s:
        return f"min_runtime schützt ({device.switch_age_s:.0f}s/{device.min_runtime_s:.0f}s)"
    if device.candidate_on:
        return f"off_delay läuft ({device.off_since_next})"
    return None


# ---------------------------------------------------------------------------
# HAUPTFUNKTION
# ---------------------------------------------------------------------------

def run_ems(st: StateProxy) -> Dict:
    """
    Run one EMS cycle against the given state snapshot.

    Returns:
        {
            "status":    { ... },          # data for the web UI
            "write_ops": [(domain, service, data), ...]
        }
    """
    now_ts = datetime.datetime.now().timestamp()
    now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_ops: List[Tuple[str, str, Dict]] = []

    debug_output            = st.get(HA_DEBUG_OUTPUT) == "on"
    ems_enabled             = st.get(HA_EMS_ENABLED) == "on"
    global_mode             = st.get(HA_GLOBAL_MODE) or "aus"
    global_puffer           = _safe_float(st.get(HA_GLOBAL_PUFFER_W))
    global_einschaltreserve = _safe_float(st.get(HA_GLOBAL_EINSCHALTRESERVE_W))

    residual_raw          = st.get(HA_RESIDUAL_W)
    residual_sensor_valid = residual_raw not in ("unavailable", "unknown", None)
    residual_w            = _safe_float(residual_raw) if residual_sensor_valid else 0.0
    hard_lockout          = not residual_sensor_valid or residual_w <= HARD_LOCKOUT_THRESHOLD_W

    if not residual_sensor_valid:
        log.error(
            "EMS SENSOR LOCKOUT: Residual-Sensor (%s) ist '%s' – alle Verbraucher werden abgeschaltet",
            HA_RESIDUAL_W, residual_raw,
        )
    elif hard_lockout and debug_output:
        log.warning(
            "EMS LOCKOUT: residual=%.0fW <= %.0fW – alle Verbraucher werden abgeschaltet",
            residual_w, HARD_LOCKOUT_THRESHOLD_W,
        )

    devices = build_devices(st)

    for device in devices:
        device.eligible = _check_eligible(device, st, ems_enabled, global_mode, hard_lockout)

        if isinstance(device, EmsControllableDevice):
            device.actual_w              = max(_safe_float(st.get(device.entity_actual_w)), 0.0)
            device.anforderung_current_w = _safe_float(st.get(device.entity_anforderung_w))
            device.anforderung_age_s     = now_ts - _parse_ts(
                st.get(device.entity_anforderung_w + ".last_changed")
            )
            device.schutz_w = device.calc_schutz_w(global_puffer)

        elif isinstance(device, EmsBinaryDevice):
            device.actual_on    = st.get(device.entity_switch) == "on"
            device.switch_age_s = now_ts - _parse_ts(
                st.get(device.entity_switch + ".last_changed")
            )
            off_attrs           = st.getattr(device.entity_off_since)
            device.off_since_ts = _safe_float((off_attrs or {}).get("timestamp"))

    pool_w = ems_calc_pool(residual_w, devices, ems_enabled, global_mode, hard_lockout)
    current_deficit_w, binary_immediate_off = ems_calc_deficit_info(residual_w, devices)

    if current_deficit_w > 0 and debug_output:
        log.warning("EMS DEFIZIT: %.0fW  sofort_aus=%s", current_deficit_w, binary_immediate_off)

    ems_calc_binary_desired(devices, pool_w, global_einschaltreserve)

    binary_devices = [d for d in devices if isinstance(d, EmsBinaryDevice)]
    for device in binary_devices:
        ems_calc_binary_candidate(device, now_ts, now_dt, binary_immediate_off)

    for device in binary_devices:
        device.final_on = device.candidate_on

    ems_apply_priority_cascade(binary_devices)
    ems_limit_one_change(binary_devices, binary_immediate_off)

    for device in binary_devices:
        if not device.final_on:
            device.off_since_next = RESET_DT

    binary_total_w = sum(d.power_w for d in binary_devices if d.final_on)

    controllable_devices = [d for d in devices if isinstance(d, EmsControllableDevice)]
    ems_allocate_controllable(controllable_devices, pool_w, binary_total_w)

    for device in controllable_devices:
        ems_calc_ramp(device, current_deficit_w)

    # --- Write ops: binary ---
    for device in binary_devices:
        write_ops.append(("input_datetime", "set_datetime", {
            "entity_id": device.entity_off_since,
            "datetime":  device.off_since_next,
        }))
        svc = "turn_on" if device.final_on else "turn_off"
        write_ops.append(("input_boolean", svc, {"entity_id": device.entity_anforderung_an}))

        if debug_output:
            changed = device.actual_on != device.final_on
            if changed:
                direction = "AUS→AN" if device.final_on else "AN→AUS"
                log.info("EMS [%s] %s  prio=%d  pool=%.0fW  %s",
                         device.id, direction, device.priority, pool_w,
                         _binary_change_reason(device, binary_immediate_off))
            else:
                reason = _binary_protection_reason(device)
                if reason:
                    log.info("EMS [%s] BLEIBT AN (gewollt=NEIN)  prio=%d  %s",
                             device.id, device.priority, reason)

    # --- Write ops: controllable ---
    for device in controllable_devices:
        delta_w        = abs(device.new_w - device.anforderung_current_w)
        is_on_off      = (device.new_w == 0) != (device.anforderung_current_w == 0)
        skip_deadband  = is_on_off or device.deadband_w <= 0

        if skip_deadband or delta_w >= device.deadband_w:
            write_ops.append(("input_number", "set_value", {
                "entity_id": device.entity_anforderung_w,
                "value":     device.new_w,
            }))
        else:
            device.new_w = device.anforderung_current_w

        if debug_output and int(device.new_w) != int(device.anforderung_current_w):
            log.info("EMS [%s] %.0fW→%.0fW  prio=%d  alloc=%.0fW  pool=%.0fW",
                     device.id, device.anforderung_current_w, device.new_w,
                     device.priority, device.alloc_w, pool_w)

    # --- Status dict for the web UI ---
    device_statuses = []
    for d in controllable_devices:
        device_statuses.append({
            "type": "controllable",
            "id": d.id,
            "priority": d.priority,
            "eligible": d.eligible,
            "actual_w": d.actual_w,
            "anforderung_current_w": d.anforderung_current_w,
            "alloc_w": d.alloc_w,
            "new_w": d.new_w,
            "schutz_w": d.schutz_w,
        })
    for d in binary_devices:
        device_statuses.append({
            "type": "binary",
            "id": d.id,
            "priority": d.priority,
            "eligible": d.eligible,
            "power_w": d.power_w,
            "actual_on": d.actual_on,
            "desired_on": d.desired_on,
            "candidate_on": d.candidate_on,
            "final_on": d.final_on,
        })

    return {
        "status": {
            "ems_enabled":          ems_enabled,
            "global_mode":          global_mode,
            "hard_lockout":         hard_lockout,
            "residual_sensor_valid": residual_sensor_valid,
            "residual_w":           residual_w,
            "pool_w":               pool_w,
            "current_deficit_w":    current_deficit_w,
            "binary_immediate_off": binary_immediate_off,
            "binary_total_w":       binary_total_w,
            "devices":              device_statuses,
            "timestamp":            now_dt,
        },
        "write_ops": write_ops,
    }
