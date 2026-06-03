"""
EMS device hierarchy.

Device (ABC)
├── ControllableDevice  – stufenlose Leistungsregelung (Heizstab, Wallbox)
└── BinaryDevice        – AN/AUS mit Zeitschutz (Heizlüfter)

Für einen neuen Gerätetyp: Klasse von Device ableiten, in controller._build_devices() eintragen.
Kein weiterer Code muss angefasst werden.
"""

import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from .state import StateProxy, safe_float, parse_ts

log = logging.getLogger(__name__)


class Device(ABC):
    """Abstract base for all EMS-managed devices."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        self.id            = id
        self.label         = label or id
        self.priority: int = 99
        self.eligible      = False
        self._allowed_modes  = allowed_modes
        self._entity_prefix  = entity_prefix or id

    # ------------------------------------------------------------------
    # Eligibility (global + per-device freigabe/modus)
    # ------------------------------------------------------------------

    def check_eligible(self, st: StateProxy,
                       ems_enabled: bool, global_mode: str, hard_lockout: bool) -> bool:
        if not ems_enabled or hard_lockout or global_mode == "aus":
            return False
        if global_mode not in self._allowed_modes:
            return False
        return self._device_eligible(st)

    def _device_eligible(self, st: StateProxy) -> bool:
        pfx = self._entity_prefix
        freigabe = st.get(f"input_boolean.ems_{pfx}_freigabe") == "on"
        modus    = st.get(f"input_select.ems_{pfx}_modus")    == "auto"
        return freigabe and modus

    # ------------------------------------------------------------------
    # Polymorphic interface – implemented by each subclass
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def current_w(self) -> float:
        """Actual power draw used for pool back-calculation."""

    @property
    def max_relief_w(self) -> float:
        """Max power that can be shed immediately (for binary_immediate_off check)."""
        return 0.0

    @abstractmethod
    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        """Refresh config params and runtime sensor values from the HA state snapshot."""

    def consume_from_pool(self, remaining_w: float,
                          global_einschaltreserve_w: float) -> float:
        """Reserve / consume power from the prioritised pool. Returns updated remaining_w."""
        return remaining_w

    def allocate(self, remaining_w: float) -> float:
        """Claim a slice of the remaining pool. Returns updated remaining_w."""
        return remaining_w

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Rate-limit the setpoint change. No-op for non-controllable devices."""

    @abstractmethod
    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        """Return HA service calls: [(domain, service, data), ...]"""

    @abstractmethod
    def to_status_dict(self) -> Dict:
        """Snapshot for the web-UI /api/status endpoint."""


# =============================================================================
# ControllableDevice – stufenlose Leistungssteuerung
# =============================================================================

class ControllableDevice(Device):
    """Continuously variable setpoint device (e.g. Heizstab, Wallbox).

    output_unit='watt':   HA helpers use _w suffix; all values in Watts.
    output_unit='ampere': HA helpers use _a suffix for device-specific limits;
                          values are converted W↔A using current phase count × voltage.
                          Phase count is selected each cycle and written to
                          input_number.ems_<prefix>_anzahl_phase.
    """

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_actual_w: str, entity_anforderung_w: str,
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None,
                 output_unit: str = 'watt',
                 allowed_phases: Optional[List[int]] = None,
                 voltage_l1_entity: Optional[str] = None,
                 voltage_l2_entity: Optional[str] = None,
                 voltage_l3_entity: Optional[str] = None,
                 phase_switch_delay_s: float = 300.0):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_actual_w      = entity_actual_w
        self.entity_anforderung_w = entity_anforderung_w
        self.output_unit          = output_unit if output_unit in ('watt', 'ampere') else 'watt'
        self._allowed_phases               = sorted(set(allowed_phases or [1]))
        self.voltage_l1_entity             = voltage_l1_entity
        self.voltage_l2_entity             = voltage_l2_entity
        self.voltage_l3_entity             = voltage_l3_entity
        # Config fallback for phase switch delay; HA entity overrides each cycle
        self._config_phase_switch_delay_s  = float(phase_switch_delay_s) if phase_switch_delay_s else 0.0
        self.phase_switch_delay_s          = self._config_phase_switch_delay_s or 30.0

        # ---- Config params (Watts; refreshed every cycle via _apply_raw_to_watt) ----
        self.min_technisch_w               = 0.0
        self.max_technisch_w               = 0.0
        self.geschuetzte_mindestleistung_w  = 0.0
        self.reserve_w                     = 0.0
        self.hoch_regelzeit_s              = 60.0
        self.runter_regelzeit_s            = 60.0
        self.max_anderung_pro_schritt_w    = 1000.0
        self.deadband_w                    = 0.0

        # ---- Raw values in native unit (A or W) read from HA; converted to W per cycle ----
        self._raw_min        = 0.0
        self._raw_max        = 0.0
        self._raw_geschuetzt = 0.0
        self._raw_max_change = 1000.0
        self._raw_deadband   = 0.0

        # ---- Runtime state ----
        self._actual_w              = 0.0
        self._anforderung_current_w = 0.0  # always Watts internally
        self._anforderung_age_s     = 0.0
        self._schutz_w              = 0.0
        self._voltage_l1            = 230.0
        self._voltage_l2            = 230.0
        self._voltage_l3            = 230.0
        self._global_puffer_w       = 0.0
        self._current_phases        = self._allowed_phases[0]
        self._ha_phases             = self._allowed_phases[0]  # phases last read from HA
        self._last_phase_change_ts  = 0.0

        # ---- Per-cycle results ----
        self._alloc_w = 0.0
        self._new_w   = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _suf(self, base: str) -> str:
        """Return HA helper suffix with correct unit: base_a (Ampere) or base_w (Watt)."""
        return f"{base}_{'a' if self.output_unit == 'ampere' else 'w'}"

    def _eff_for(self, phases: int) -> float:
        """Watts per Ampere for a given phase count using per-phase voltages.

        1-phase: P = I × V_L1
        3-phase: P = I × (V_L1 + V_L2 + V_L3)
        """
        if self.output_unit != 'ampere':
            return 1.0
        if phases == 1:
            return self._voltage_l1
        return self._voltage_l1 + self._voltage_l2 + self._voltage_l3

    def _eff(self) -> float:
        """Watts per Ampere for the currently selected phase count."""
        return self._eff_for(self._current_phases)

    def _apply_raw_to_watt(self) -> None:
        """Convert raw native-unit values to Watts using _current_phases × _voltage_v.

        Also recomputes _schutz_w so that consume_from_pool always uses a consistent value
        even when called after a mid-cycle phase change via select_phases().
        """
        eff = self._eff()
        if self.output_unit == 'ampere':
            self.min_technisch_w              = self._raw_min        * eff
            self.max_technisch_w              = self._raw_max        * eff
            self.geschuetzte_mindestleistung_w = self._raw_geschuetzt * eff
            self.max_anderung_pro_schritt_w   = self._raw_max_change * eff
            self.deadband_w                   = self._raw_deadband   * eff
        else:
            self.min_technisch_w              = self._raw_min
            self.max_technisch_w              = self._raw_max
            self.geschuetzte_mindestleistung_w = self._raw_geschuetzt
            self.max_anderung_pro_schritt_w   = self._raw_max_change
            self.deadband_w                   = self._raw_deadband
        self._schutz_w = min(
            self.geschuetzte_mindestleistung_w + self.reserve_w + self._global_puffer_w,
            self.max_technisch_w,
        )

    # ------------------------------------------------------------------
    # Exposed read-only state for controller logging
    # ------------------------------------------------------------------

    @property
    def anforderung_current_w(self) -> float:
        return self._anforderung_current_w

    @property
    def new_w(self) -> float:
        return self._new_w

    @property
    def alloc_w(self) -> float:
        return self._alloc_w

    # ------------------------------------------------------------------
    # Device interface
    # ------------------------------------------------------------------

    @property
    def current_w(self) -> float:
        return self._actual_w

    @property
    def max_relief_w(self) -> float:
        return max(self._actual_w - self.min_technisch_w, 0.0) if self.eligible else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        pfx = self._entity_prefix
        self._global_puffer_w = global_puffer_w

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        # Phase voltages – plausibility check 180–260 V each, fallback 230 V
        def _read_v(entity: Optional[str]) -> float:
            if not entity:
                return 230.0
            v = safe_float(st.get(entity), 0.0)
            return v if 180.0 < v < 260.0 else 230.0

        self._voltage_l1 = _read_v(self.voltage_l1_entity)
        self._voltage_l2 = _read_v(self.voltage_l2_entity)
        self._voltage_l3 = _read_v(self.voltage_l3_entity)

        # Phase switch delay: HA entity > config value > 30 s hard default
        if self.output_unit == 'ampere' and len(self._allowed_phases) > 1:
            raw_delay = st.get(f"input_number.ems_{pfx}_min_umschaltzeit_s")
            if raw_delay not in (None, "unavailable", "unknown"):
                ha_delay = safe_float(raw_delay, 0.0)
                self.phase_switch_delay_s = ha_delay if ha_delay > 0 else (self._config_phase_switch_delay_s or 30.0)
            else:
                self.phase_switch_delay_s = self._config_phase_switch_delay_s or 30.0

        # HA phase count written last cycle – used for correct anforderung read-back
        if self.output_unit == 'ampere' and len(self._allowed_phases) > 1:
            ha_ph = int(safe_float(
                st.get(f"input_number.ems_{pfx}_anzahl_phase"), self._current_phases
            ))
            self._ha_phases = ha_ph if ha_ph in self._allowed_phases else self._current_phases
        else:
            self._ha_phases = self._current_phases

        self.priority           = int(n("prioritat", self.priority))
        self.reserve_w          = n("reserve_w")
        self.hoch_regelzeit_s   = n("hoch_regelzeit_s")
        self.runter_regelzeit_s = n("runter_regelzeit_s")

        # Read raw values in native unit (_a or _w depending on output_unit)
        self._raw_min        = n(self._suf("min_technisch"))
        self._raw_max        = n(self._suf("max_technisch"))
        self._raw_geschuetzt = n(self._suf("geschutzte_mindestleistung"))
        self._raw_max_change = n(self._suf("max_anderung_pro_schritt"), 1000.0)
        self._raw_deadband   = n(self._suf("min_anderung_pro_schritt"), 0.0)

        # Convert to Watts using current phase count (may be updated by select_phases later)
        self._apply_raw_to_watt()

        self._actual_w = max(safe_float(st.get(self.entity_actual_w)), 0.0)

        # Read setpoint; convert from native unit to Watts using HA phase count for accuracy
        raw_anf = safe_float(st.get(self.entity_anforderung_w))
        if self.output_unit == 'ampere':
            self._anforderung_current_w = raw_anf * self._eff_for(self._ha_phases)
        else:
            self._anforderung_current_w = raw_anf

        self._anforderung_age_s = now_ts - parse_ts(
            st.get(self.entity_anforderung_w + ".last_changed")
        )

    def select_phases(self, pool_w: float, now_ts: float) -> None:
        """Select phase count for this cycle using reluctant-switching strategy.

        Initial start (setpoint == 0): greedy – pick highest phase count the pool supports.
        Active charging (setpoint > 0):
          - Stay on current phases while they can still meet the minimum.
          - Switch UP only when current phases are fully maxed out (pool exceeds max_a).
          - Switch DOWN only when current phases can no longer meet min_a.
        Hysteresis timer applies only during active charging, not on initial start.
        """
        if self.output_unit != 'ampere' or len(self._allowed_phases) == 1 or not self.eligible:
            return

        is_initial_start = self._anforderung_current_w == 0

        # Hysteresis only applies during active charging
        if not is_initial_start:
            if (self._last_phase_change_ts > 0 and
                    now_ts - self._last_phase_change_ts < self.phase_switch_delay_s):
                return

        if is_initial_start:
            # Greedy: highest phase count the pool can support at minimum threshold
            selected = min(self._allowed_phases)  # fallback to lowest
            for ph in sorted(self._allowed_phases, reverse=True):
                eff = self._eff_for(ph)
                if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                    selected = ph
                    break
            reason = "Ladestart"
        else:
            # Reluctant: only switch when forced
            eff_cur = self._eff_for(self._current_phases)
            can_sustain = eff_cur > 0 and math.floor(pool_w / eff_cur) >= self._raw_min

            if can_sustain:
                # Switch UP only if current phases are at maximum capacity
                higher = [ph for ph in self._allowed_phases if ph > self._current_phases]
                if (higher and self._raw_max > 0 and eff_cur > 0
                        and math.floor(pool_w / eff_cur) >= self._raw_max):
                    selected = self._current_phases  # stay unless a higher phase works
                    for ph in sorted(higher):
                        eff = self._eff_for(ph)
                        if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                            selected = ph
                            break
                    reason = "Hochschalten (max erreicht)"
                else:
                    selected = self._current_phases  # stay – no reason to switch
                    reason = ""
            else:
                # Switch DOWN: current phases can no longer meet minimum
                lower = [ph for ph in self._allowed_phases if ph < self._current_phases]
                selected = min(self._allowed_phases)  # fallback
                for ph in sorted(lower):
                    eff = self._eff_for(ph)
                    if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                        selected = ph
                        break
                reason = "Runterschalten (min unterschritten)"

        if selected != self._current_phases:
            log.info("EMS [%s] Phasenwechsel %d→%d  pool=%.0fW  L1=%.1fV L2=%.1fV L3=%.1fV  (%s)",
                     self.id, self._current_phases, selected, pool_w,
                     self._voltage_l1, self._voltage_l2, self._voltage_l3, reason)
            self._current_phases = selected
            self._last_phase_change_ts = now_ts
            self._apply_raw_to_watt()
            self._anforderung_age_s = 0.0

    def consume_from_pool(self, remaining_w: float, _: float) -> float:
        """Reserve schutz_w so binary devices cannot consume it."""
        return remaining_w - self._schutz_w if self.eligible else remaining_w

    def allocate(self, remaining_w: float) -> float:
        """Claim up to max_technisch_w from the remaining pool."""
        if not self.eligible or remaining_w <= 0:
            self._alloc_w = 0.0
            return remaining_w
        if self.min_technisch_w == 0 or remaining_w >= self.min_technisch_w:
            self._alloc_w = min(remaining_w, self.max_technisch_w)
        else:
            self._alloc_w = 0.0
        return remaining_w - self._alloc_w

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Apply ramp-rate limiting; result stored in _new_w."""
        if not self.eligible:
            self._new_w = 0.0
            return

        ideal_w   = self._alloc_w
        current_w = self._anforderung_current_w
        age_s     = self._anforderung_age_s

        if ideal_w > current_w:
            new_w = (
                min(ideal_w, current_w + self.max_anderung_pro_schritt_w, self.max_technisch_w)
                if age_s >= self.hoch_regelzeit_s else current_w
            )
        elif ideal_w < current_w:
            if current_deficit_w > 0:
                new_w = ideal_w  # immediate ramp-down on deficit
            else:
                new_w = (
                    max(ideal_w, current_w - self.max_anderung_pro_schritt_w)
                    if age_s >= self.runter_regelzeit_s else current_w
                )
        else:
            new_w = current_w

        if 0 < new_w < self.min_technisch_w:
            new_w = self.min_technisch_w if ideal_w >= self.min_technisch_w else 0.0

        self._new_w = round(max(min(new_w, self.max_technisch_w), 0.0))

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        delta     = abs(self._new_w - self._anforderung_current_w)
        is_on_off = (self._new_w == 0) != (self._anforderung_current_w == 0)
        # Only write when value actually changes – writing the same value every cycle
        # would reset last_changed and prevent anforderung_age_s from aging correctly,
        # which breaks hoch_regelzeit_s / runter_regelzeit_s ramp timing.
        write = is_on_off or (delta > 0 and (self.deadband_w <= 0 or delta >= self.deadband_w))

        ops: List[Tuple[str, str, Dict]] = []

        # Write phase count only when it changed (keeps HA write count low)
        if self.output_unit == 'ampere' and self._current_phases != self._ha_phases:
            ops.append(("input_number", "set_value", {
                "entity_id": f"input_number.ems_{self._entity_prefix}_anzahl_phase",
                "value":     float(self._current_phases),
            }))

        if write:
            eff   = self._eff()
            value = math.floor(self._new_w / eff) if self.output_unit == 'ampere' and eff > 0 else self._new_w
            ops.append(("input_number", "set_value", {
                "entity_id": self.entity_anforderung_w,
                "value":     value,
            }))
        else:
            self._new_w = self._anforderung_current_w  # deadband active – no write

        return ops

    def to_status_dict(self) -> Dict:
        d: Dict = {
            "type":                  "controllable",
            "id":                    self.id,
            "label":                 self.label,
            "priority":              self.priority,
            "eligible":              self.eligible,
            "actual_w":              self._actual_w,
            "anforderung_current_w": self._anforderung_current_w,
            "alloc_w":               self._alloc_w,
            "new_w":                 self._new_w,
            "schutz_w":              self._schutz_w,
            "output_unit":           self.output_unit,
        }
        if self.output_unit == 'ampere':
            eff = self._eff()
            d["current_phases"]  = self._current_phases
            d["allowed_phases"]  = self._allowed_phases
            d["voltage_l1"]      = round(self._voltage_l1, 1)
            d["voltage_l2"]      = round(self._voltage_l2, 1)
            d["voltage_l3"]      = round(self._voltage_l3, 1)
            d["new_a"]           = math.floor(self._new_w / eff) if eff > 0 else 0
            if len(self._allowed_phases) > 1 and self._last_phase_change_ts > 0:
                remaining = self.phase_switch_delay_s - (time.time() - self._last_phase_change_ts)
                d["phase_lock_remaining_s"] = max(0.0, round(remaining))
        return d


# =============================================================================
# BinaryDevice – binärer Verbraucher mit Zeitschutz
# =============================================================================

class BinaryDevice(Device):
    """On/off device with min_runtime, min_offtime, and off_delay guards."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_switch: str, entity_anforderung_an: str,
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_switch         = entity_switch
        self.entity_anforderung_an = entity_anforderung_an

        # ---- Config params (refreshed from HA each cycle) ----
        self.power_w       = 0.0
        self.on_reserve_w  = 0.0
        self.min_runtime_s = 0.0
        self.min_offtime_s = 0.0
        self.off_delay_s   = 0.0

        # ---- Runtime state (read from HA each cycle) ----
        self._actual_on    = False
        self._switch_age_s = 0.0

        # ---- Internal persistent state (survives across cycles) ----
        self._off_since_ts: float = 0.0

        # ---- Per-cycle computation ----
        self._desired_on   = False
        self._candidate_on = False
        self._final_on     = False

    # --- Exposed state for controller ---

    @property
    def actual_on(self) -> bool:
        return self._actual_on

    @property
    def desired_on(self) -> bool:
        return self._desired_on

    @property
    def candidate_on(self) -> bool:
        return self._candidate_on

    @property
    def final_on(self) -> bool:
        return self._final_on

    @final_on.setter
    def final_on(self, value: bool) -> None:
        self._final_on = value

    @property
    def in_min_runtime(self) -> bool:
        return self._actual_on and self._switch_age_s < self.min_runtime_s

    # --- Device interface ---

    @property
    def current_w(self) -> float:
        return self.power_w if self._actual_on else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        pfx = self._entity_prefix

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        self.priority      = int(n("prioritat", self.priority))
        self.power_w       = n("leistung_w")
        self.on_reserve_w  = n("einschaltreserve_w")
        self.min_runtime_s = n("mindestlaufzeit_s")
        self.min_offtime_s = n("mindestauszeit_s")
        self.off_delay_s   = n("abschaltverzogerung_s")

        self._actual_on    = st.get(self.entity_switch) == "on"
        self._switch_age_s = now_ts - parse_ts(
            st.get(self.entity_switch + ".last_changed")
        )

    def consume_from_pool(self, remaining_w: float,
                          global_einschaltreserve_w: float) -> float:
        """Determine desired state via hysteresis; consume power_w if desired on."""
        if not self.eligible:
            return remaining_w
        on_threshold = self.power_w + self.on_reserve_w + global_einschaltreserve_w
        if self._actual_on:
            self._desired_on = remaining_w >= self.power_w
        else:
            self._desired_on = remaining_w >= on_threshold
        return remaining_w - self.power_w if self._desired_on else remaining_w

    def calculate_candidate(self, now_ts: float,
                             binary_immediate_off: bool) -> None:
        """Apply timing guards (min_runtime, off_delay, min_offtime) to desired state."""
        if not self.eligible:
            self._candidate_on = False
            self._off_since_ts = 0.0
            return

        if self._actual_on:
            if self._desired_on:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

            if binary_immediate_off:
                # Mindestlaufzeit schützt auch bei Notabschaltung
                if self._switch_age_s < self.min_runtime_s:
                    self._candidate_on = True
                    self._off_since_ts = 0.0
                else:
                    self._candidate_on = False
                return

            if self._switch_age_s < self.min_runtime_s:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

            if self._off_since_ts <= 0:
                self._off_since_ts = now_ts

            pending_elapsed = now_ts - self._off_since_ts
            if self.off_delay_s == 0 or pending_elapsed >= self.off_delay_s:
                self._candidate_on = False
            else:
                self._candidate_on = True
        else:
            self._off_since_ts = 0.0
            self._candidate_on = (
                self._desired_on and self._switch_age_s >= self.min_offtime_s
            )

    def reset_off_timer(self) -> None:
        """Reset the off_delay timer. Called after priority cascade when device goes OFF."""
        self._off_since_ts = 0.0

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        svc = "turn_on" if self._final_on else "turn_off"
        return [("input_boolean", svc, {"entity_id": self.entity_anforderung_an})]

    def to_status_dict(self) -> Dict:
        return {
            "type":           "binary",
            "id":             self.id,
            "label":          self.label,
            "priority":       self.priority,
            "eligible":       self.eligible,
            "power_w":        self.power_w,
            "actual_on":      self._actual_on,
            "desired_on":     self._desired_on,
            "candidate_on":   self._candidate_on,
            "final_on":       self._final_on,
            "in_min_runtime": self.in_min_runtime,
            "switch_age_s":   round(self._switch_age_s),
            "min_runtime_s":  self.min_runtime_s,
            "min_offtime_s":  self.min_offtime_s,
        }
